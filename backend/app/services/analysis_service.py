"""The analysis pipeline: enrich, compute, value, score, explain.

The orchestration layer, and the only place that is allowed to know about both
engines and providers. Engines stay pure; this service is what feeds them.

Stage order matters and is fixed (``ARCHITECTURE.md`` §3): money and scoring finish
before the AI layer is handed anything, so a model cannot influence a number, only
describe one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from app.core.money import Cents, cents
from app.engines.base import EngineResult
from app.engines.financial.contracts import (
    BuyerFinancials,
    MortgageTerms,
    PropertyFinancials,
    PropertyKind,
    ResidencyStatus,
)
from app.engines.financial.engine import DeterministicFinancialEngine
from app.engines.rules import RuleSet
from app.engines.scoring.contracts import BuyScore, CappedAdjustment, Component, Factor
from app.engines.scoring.engine import aggregate, modifiers_for, unavailable
from app.engines.scoring.subscores import (
    affordability_subscore,
    personal_fit_subscore,
    property_quality_subscore,
    qualification_factors,
    risk_subscore,
    value_subscore,
)
from app.engines.valuation.contracts import Comparable, RiskFlag
from app.engines.valuation.engine import compute_fair_value, score_comparable, suggested_offer
from app.schemas.analysis import (
    AnalyzeRequest,
    AnalyzeResponse,
    AssumptionOut,
    FactorOut,
    FairValueOut,
    MoneyOut,
    QualificationOut,
    RiskOut,
    ScoreOut,
    TraceOut,
)


class AnalysisService:
    def __init__(self, rules: RuleSet, financial: DeterministicFinancialEngine | None = None):
        self.rules = rules
        self.financial = financial or DeterministicFinancialEngine()

    def analyze(
        self,
        request: AnalyzeRequest,
        *,
        as_of: date,
        risk_flags: tuple[RiskFlag, ...] = (),
        condition_adjustment: CappedAdjustment | None = None,
        risk_adjustment: CappedAdjustment | None = None,
    ) -> AnalyzeResponse:
        property_ = PropertyFinancials(
            purchase_price_cents=cents(request.property.purchase_price_cents),
            jurisdiction=request.property.jurisdiction,
            property_kind=PropertyKind(request.property.property_kind),
            annual_property_tax_cents=_opt_cents(request.property.annual_property_tax_cents),
            monthly_condo_fee_cents=_opt_cents(request.property.monthly_condo_fee_cents),
            square_feet=request.property.square_feet,
            is_new_build=request.property.is_new_build,
        )
        buyer = BuyerFinancials(
            gross_annual_income_cents=cents(request.buyer.gross_annual_income_cents),
            household_income_cents=cents(request.buyer.household_income_cents),
            monthly_debt_payments_cents=cents(request.buyer.monthly_debt_payments_cents),
            down_payment_cents=cents(request.buyer.down_payment_cents),
            available_savings_cents=cents(request.buyer.available_savings_cents),
            emergency_fund_cents=cents(request.buyer.emergency_fund_cents),
            desired_max_monthly_cents=_opt_cents(request.buyer.desired_max_monthly_cents),
            first_time_buyer=request.buyer.first_time_buyer,
            residency_status=ResidencyStatus(request.buyer.residency_status),
        )
        terms = MortgageTerms(
            contract_rate=request.terms.contract_rate,
            amortization_years=request.terms.amortization_years,
        )

        # --- money, deterministically -------------------------------------------------
        mortgage = self.financial.mortgage(
            property_=property_, buyer=buyer, terms=terms, rules=self.rules, as_of=as_of
        )
        closing = self.financial.closing_costs(
            property_=property_,
            buyer=buyer,
            mortgage=mortgage.value,
            rules=self.rules,
            as_of=as_of,
        )
        ownership = self.financial.ownership_cost(
            property_=property_, mortgage=mortgage.value, rules=self.rules, as_of=as_of
        )
        qualification = self.financial.qualification(
            property_=property_,
            buyer=buyer,
            terms=terms,
            ownership=ownership.value,
            rules=self.rules,
            as_of=as_of,
        )
        affordability = self.financial.affordability(
            buyer=buyer,
            ownership=ownership.value,
            closing=closing.value,
            mortgage=mortgage.value,
        )

        # --- value -----------------------------------------------------------------
        scored_comps = tuple(
            score_comparable(
                subject_square_feet=request.property.square_feet,
                subject_bedrooms=request.property.bedrooms,
                comparable=Comparable(
                    address=c.address,
                    sale_price_cents=cents(c.sale_price_cents),
                    sale_date=date.fromisoformat(c.sale_date),
                    bedrooms=c.bedrooms,
                    square_feet=c.square_feet,
                ),
                distance_m=c.distance_m,
                as_of=as_of,
            )
            for c in request.comparables
        )
        fair_value = compute_fair_value(
            asking_price_cents=property_.purchase_price_cents,
            comparables=scored_comps,
            subject_square_feet=request.property.square_feet,
        )
        offer_low, offer_high = suggested_offer(
            fair_value=fair_value.value, asking_price_cents=property_.purchase_price_cents
        )

        # --- score ------------------------------------------------------------------
        preferences = request.preferences
        subscores = [
            affordability_subscore(affordability.value),
            value_subscore(
                asking_cents=property_.purchase_price_cents, fair_value=fair_value.value
            ),
            personal_fit_subscore(
                bedrooms=request.property.bedrooms,
                min_bedrooms=preferences.min_bedrooms,
                bathrooms=request.property.bathrooms,
                min_bathrooms=preferences.min_bathrooms,
                has_parking=request.property.has_parking,
                requires_parking=preferences.requires_parking,
                commute_minutes=preferences.commute_minutes,
                max_commute_minutes=preferences.max_commute_minutes,
            ),
            unavailable(
                Component.LOCATION,
                "Location metrics need the OpenStreetMap services, which are not "
                "configured in this environment.",
            ),
            property_quality_subscore(
                year_built=request.property.year_built,
                as_of_year=as_of.year,
                square_feet=request.property.square_feet,
                adjustment=condition_adjustment,
            ),
            unavailable(
                Component.INVESTMENT,
                "No rental assumptions supplied, so cash flow and yield cannot be computed.",
            ),
            risk_subscore(risk_flags, risk_adjustment),
            unavailable(
                Component.MARKET,
                "No dated market snapshot for this jurisdiction yet.",
            ),
        ]

        buy = aggregate(
            subscores=tuple(subscores),
            modifiers=modifiers_for(
                goal=preferences.goal,
                horizon=preferences.time_horizon,
                risk_posture=preferences.risk_posture,
                has_children=preferences.has_children,
                schools_importance=preferences.schools_importance,
                budget_pressure=_budget_pressure(request, ownership.value.total_monthly_cents),
            ),
        )

        results: tuple[EngineResult[Any], ...] = (
            mortgage,
            closing,
            ownership,
            qualification,
            affordability,
            fair_value,
        )
        extra_factors = qualification_factors(qualification.value)
        return self._render(
            request=request,
            buy=buy,
            results=results,
            extra_factors=extra_factors,
            mortgage=mortgage.value,
            closing=closing.value,
            ownership=ownership.value,
            qualification=qualification.value,
            affordability=affordability.value,
            fair_value=fair_value.value,
            offer=(offer_low, offer_high),
            risk_flags=risk_flags,
            scored_comps=scored_comps,
            as_of=as_of,
        )

    def _render(self, **kw: Any) -> AnalyzeResponse:
        buy: BuyScore = kw["buy"]
        results = kw["results"]
        request: AnalyzeRequest = kw["request"]

        factors: dict[str, list[FactorOut]] = {"positive": [], "negative": []}
        for subscore in buy.subscores:
            for factor in subscore.factors:
                _bucket(factors, factor)
        for factor in kw["extra_factors"]:
            _bucket(factors, factor)

        traces = [
            TraceOut(
                name=step.name,
                formula=step.formula,
                inputs=_jsonable(step.inputs),
                output=_jsonable(step.output),
                unit=step.unit,
                rule_keys=list(step.rule_keys),
            )
            for result in results
            for step in result.steps
        ]
        assumptions = [
            AssumptionOut(key=a.key, value=_jsonable(a.value), rationale=a.rationale)
            for result in results
            for a in result.assumptions
        ]
        unavailable_facts = [
            {"reason": fact.provenance.unavailable_reason or "unstated"}
            for result in results
            for fact in result.unavailable
        ] + [
            {"component": s.component.value, "reason": s.unavailable_reason or "unstated"}
            for s in buy.subscores
            if not s.available
        ]

        return AnalyzeResponse(
            scoring_model_version=buy.scoring_model_version,
            rule_set=self.rules.label,
            buy_score=buy.buy_score,
            score_withheld_reason=buy.withheld_reason,
            confidence=float(buy.confidence),
            inputs_hash=_inputs_hash(request, self.rules.label, buy.scoring_model_version),
            scores=[
                ScoreOut(
                    component=s.component.value,
                    available=s.available,
                    subscore=float(s.score) if s.score is not None else None,
                    base_weight=float(s.base_weight),
                    effective_weight=float(s.effective_weight),
                    contribution=float(s.contribution),
                    confidence=float(s.confidence),
                    unavailable_reason=s.unavailable_reason,
                )
                for s in buy.subscores
            ],
            factors=factors,
            money=MoneyOut(
                purchase_price_cents=request.property.purchase_price_cents,
                down_payment_cents=request.buyer.down_payment_cents,
                mortgage_principal_cents=kw["mortgage"].principal_cents,
                insurance_premium_cents=kw["mortgage"].insurance_premium_cents,
                monthly_ownership_cost_cents=kw["ownership"].total_monthly_cents,
                closing_costs_cents=kw["closing"].total_cents,
                cash_required_cents=kw["affordability"].cash_required_cents,
                cash_shortfall_cents=kw["affordability"].cash_shortfall_cents,
            ),
            closing_cost_lines=[
                {
                    "key": line.key,
                    "label": line.label,
                    "amount_cents": line.amount_cents,
                    "is_estimate": line.is_estimate,
                    "rule_keys": list(line.rule_keys),
                }
                for line in kw["closing"].lines
            ],
            qualification=QualificationOut(
                may_qualify=kw["qualification"].may_qualify,
                stressed_rate=float(kw["qualification"].stressed_rate),
                gds=float(kw["qualification"].gds),
                tds=float(kw["qualification"].tds),
                gds_limit=float(kw["qualification"].gds_limit),
                tds_limit=float(kw["qualification"].tds_limit),
                insured_eligible=kw["qualification"].insured_eligible,
                max_purchase_price_cents=kw["qualification"].max_purchase_price_cents,
                blocking_reasons=list(kw["qualification"].blocking_reasons),
                disclaimer=kw["qualification"].disclaimer,
            ),
            fair_value=FairValueOut(
                low_cents=kw["fair_value"].low_cents,
                high_cents=kw["fair_value"].high_cents,
                basis=kw["fair_value"].basis.value,
                confidence=float(kw["fair_value"].confidence),
                note=kw["fair_value"].note,
            ),
            risks=[
                RiskOut(
                    category=f.category.value,
                    status=f.status.value,
                    severity=f.severity.value,
                    evidence=f.evidence,
                    explanation=f.explanation,
                    recommended_action=f.recommended_action,
                    distance_m=f.distance_m,
                )
                for f in kw["risk_flags"]
            ],
            traces=traces,
            assumptions=assumptions,
            unavailable=unavailable_facts,
        )


def _bucket(factors: dict[str, list[FactorOut]], factor: Factor) -> None:
    out = FactorOut(
        component=factor.component.value,
        direction=factor.direction.value,
        magnitude=float(factor.magnitude),
        sentence=factor.sentence,
    )
    factors["positive" if factor.direction.value == "positive" else "negative"].append(out)


def _opt_cents(value: int | None) -> Cents | None:
    return cents(value) if value is not None else None


def _budget_pressure(request: AnalyzeRequest, monthly_cost: int) -> bool:
    budget = request.buyer.desired_max_monthly_cents
    return bool(budget and monthly_cost >= budget * 0.9)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    return value


def _inputs_hash(request: AnalyzeRequest, rule_set: str, model_version: str) -> str:
    """The reproducibility fingerprint: same bundle, same versions, same score."""
    payload = json.dumps(
        {
            "request": request.model_dump(mode="json"),
            "rule_set": rule_set,
            "scoring_model_version": model_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()
