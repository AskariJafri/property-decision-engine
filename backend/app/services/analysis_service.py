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
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.core.money import Cents, cents
from app.engines.base import EngineResult
from app.engines.comparables.engine import build_grid
from app.engines.financial.contracts import (
    AffordabilityResult,
    BuyerFinancials,
    MortgageResult,
    MortgageTerms,
    OwnershipCostResult,
    PropertyFinancials,
    PropertyKind,
    ResidencyStatus,
)
from app.engines.financial.engine import DeterministicFinancialEngine
from app.engines.risk.missing_info import MissingInfoInput, missing_information
from app.engines.rules import RuleSet
from app.engines.scenarios.personal import PersonalInput, personal_fit
from app.engines.scoring.contracts import BuyScore, CappedAdjustment, Component, Factor
from app.engines.scoring.engine import aggregate, modifiers_for, unavailable
from app.engines.scoring.subscores import (
    affordability_subscore,
    location_subscore,
    personal_fit_subscore,
    property_quality_subscore,
    qualification_factors,
    risk_subscore,
    value_subscore,
)
from app.engines.valuation.contracts import Comparable, RiskFlag
from app.engines.valuation.engine import compute_fair_value, score_comparable, suggested_offer
from app.schemas.analysis import (
    AdjustedComparableOut,
    AdjustmentOut,
    AnalyzeRequest,
    AnalyzeResponse,
    AssumptionOut,
    ComparableGridOut,
    DataBasis,
    FactorOut,
    FairValueOut,
    MissingItemOut,
    MoneyOut,
    MonthlyLineOut,
    PersonalOut,
    QualificationOut,
    RateScenarioOut,
    RiskOut,
    ScoreOut,
    TraceOut,
    UnadjustedAttributeOut,
)


@dataclass(frozen=True, slots=True)
class LocationFacts:
    """What the enrichment stage managed to resolve, already unwrapped.

    Resolution happens in the route handler, which may do I/O. By the time the
    service sees it, location is plain data — so the service stays synchronous and
    the engines stay pure.
    """

    commute_minutes: int | None = None
    commute_is_estimated: bool = False
    amenity_counts: dict[str, int] | None = None
    unavailable_reason: str | None = None


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
        location: LocationFacts | None = None,
    ) -> AnalyzeResponse:
        property_, buyer, terms = to_domain(request)

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
        # The adjustment grid restates each sale as an estimate of the subject before
        # anything averages them, so it has to be built first. With no comparables it
        # is an empty grid and compute_fair_value falls back to the asking-price band
        # exactly as before.
        grid = build_grid(
            comparables=scored_comps,
            subject_square_feet=request.property.square_feet,
            subject_bedrooms=request.property.bedrooms,
            as_of=as_of,
        )
        fair_value = compute_fair_value(
            asking_price_cents=property_.purchase_price_cents,
            comparables=scored_comps,
            subject_square_feet=request.property.square_feet,
            adjusted=grid.value.rows,
        )
        offer_low, offer_high = suggested_offer(
            fair_value=fair_value.value, asking_price_cents=property_.purchase_price_cents
        )

        # --- score ------------------------------------------------------------------
        preferences = request.preferences
        # Anything the ownership cost could not include understates the monthly
        # figure, which would otherwise flatter the affordability score.
        missing_costs = tuple(
            _cost_name(fact.provenance.unavailable_reason or "") for fact in ownership.unavailable
        )
        subscores = [
            affordability_subscore(affordability.value, missing_cost_components=missing_costs),
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
                commute_minutes=(
                    location.commute_minutes
                    if location and location.commute_minutes is not None
                    else preferences.commute_minutes
                ),
                max_commute_minutes=preferences.max_commute_minutes,
                # Location narrates the commute when it measured one.
                emit_commute_factor=not (location and location.commute_minutes),
            ),
            _location(location, preferences.max_commute_minutes),
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
        response = self._render(
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
            grid=grid.value,
            as_of=as_of,
        )
        self._decorate(
            response,
            request=request,
            property_=property_,
            buyer=buyer,
            terms=terms,
            mortgage=mortgage.value,
            ownership=ownership.value,
            affordability=affordability.value,
            comparables_included=sum(1 for c in scored_comps if c.included),
            as_of=as_of,
        )
        return response

    def _decorate(
        self,
        response: AnalyzeResponse,
        *,
        request: AnalyzeRequest,
        property_: PropertyFinancials,
        buyer: BuyerFinancials,
        terms: MortgageTerms,
        mortgage: MortgageResult,
        ownership: OwnershipCostResult,
        affordability: AffordabilityResult,
        comparables_included: int,
        as_of: date,
    ) -> None:
        """The free analysis's plain-language layer: labels, gaps, fit and rates.

        Everything here is derived from figures already computed above; it adds
        labels and arrangement, never a new estimate.
        """
        is_condo = property_.property_kind in (
            PropertyKind.CONDO_APARTMENT,
            PropertyKind.CONDO_TOWNHOUSE,
        )
        tax_supplied = request.property.annual_property_tax_cents is not None
        tax_basis: DataBasis = (
            "user_provided"
            if tax_supplied
            else ("estimated" if ownership.property_tax_cents > 0 else "unavailable")
        )
        tax_notes: dict[str, str] = {
            "user_provided": "From the annual figure you entered.",
            "estimated": "Estimated from the municipal rate applied to the price.",
            "unavailable": "No rate for this municipality; enter the figure from the listing.",
        }
        lines = [
            MonthlyLineOut(
                key="mortgage_payment",
                label="Mortgage payment",
                amount_cents=ownership.mortgage_payment_cents,
                basis="known",
                note="Calculated from the price, your down payment, rate and amortization.",
            ),
            MonthlyLineOut(
                key="property_tax",
                label="Property tax",
                amount_cents=ownership.property_tax_cents if tax_basis != "unavailable" else None,
                basis=tax_basis,
                note=tax_notes[tax_basis],
            ),
        ]
        if is_condo:
            fee_known = request.property.monthly_condo_fee_cents is not None
            lines.append(
                MonthlyLineOut(
                    key="condo_fee",
                    label="Condo fee",
                    amount_cents=ownership.condo_fee_cents if fee_known else None,
                    basis="user_provided" if fee_known else "unavailable",
                    note="As entered."
                    if fee_known
                    else "Not supplied, so not included in the total.",
                )
            )
        lines += [
            MonthlyLineOut(
                key="insurance",
                label="Home insurance",
                amount_cents=ownership.insurance_cents,
                basis="assumption",
                note="Planning default for an Ontario policy; replace with a quote.",
            ),
            MonthlyLineOut(
                key="utilities",
                label="Utilities",
                amount_cents=ownership.utilities_cents,
                basis="assumption",
                note="Planning default; varies with the home and season.",
            ),
            MonthlyLineOut(
                key="maintenance",
                label="Maintenance reserve",
                amount_cents=ownership.maintenance_reserve_cents,
                basis="assumption",
                note="A share of the price set aside each year for repairs.",
            ),
        ]
        response.monthly_breakdown = lines
        response.money_labels = {
            "purchase_price_cents": "user_provided",
            "down_payment_cents": "user_provided",
            "mortgage_principal_cents": "known",
            "insurance_premium_cents": "known",
            "monthly_ownership_cost_cents": "estimated",
            "closing_costs_cents": "estimated",
            "cash_required_cents": "estimated",
            "cash_shortfall_cents": "estimated",
        }

        response.missing_info = [
            MissingItemOut(
                key=item.key,
                title=item.title,
                why_it_matters=item.why_it_matters,
                what_to_ask_for=item.what_to_ask_for,
                severity=item.severity,
                category=item.category,
            )
            for item in missing_information(
                MissingInfoInput(
                    property_kind=property_.property_kind.value,
                    annual_property_tax_supplied=tax_supplied,
                    property_tax_estimated=tax_basis == "estimated",
                    monthly_condo_fee_supplied=request.property.monthly_condo_fee_cents is not None,
                    year_built=request.property.year_built,
                    as_of_year=as_of.year,
                    square_feet=request.property.square_feet,
                    bedrooms=request.property.bedrooms,
                    address_supplied=bool(request.property.address),
                    comparables_included=comparables_included,
                    is_new_build=request.property.is_new_build,
                )
            )
        ]

        fit = personal_fit(
            PersonalInput(
                gross_annual_income_cents=request.buyer.household_income_cents,
                monthly_net_income_cents=request.buyer.monthly_net_income_cents,
                monthly_debt_payments_cents=request.buyer.monthly_debt_payments_cents,
                other_monthly_expenses_cents=request.buyer.other_monthly_expenses_cents,
                monthly_housing_cost_cents=ownership.total_monthly_cents,
                cash_required_cents=affordability.cash_required_cents,
                available_savings_cents=request.buyer.available_savings_cents,
                emergency_fund_cents=request.buyer.emergency_fund_cents,
            )
        )
        response.personal = PersonalOut(
            lines=[
                MonthlyLineOut(
                    key=line.key,
                    label=line.label,
                    amount_cents=line.amount_cents,
                    basis=line.basis,
                    note=line.note,
                )
                for line in fit.lines
            ],
            housing_share_of_gross=float(fit.housing_share_of_gross),
            emergency_months=float(fit.emergency_months)
            if fit.emergency_months is not None
            else None,
        )

        scenarios = []
        for delta in (Decimal("0"), Decimal("0.01"), Decimal("0.02")):
            rate = terms.contract_rate + delta
            if rate >= 1:
                continue
            payment = (
                mortgage.payment_cents
                if not delta
                else self.financial.mortgage(
                    property_=property_,
                    buyer=buyer,
                    terms=MortgageTerms(
                        contract_rate=rate, amortization_years=terms.amortization_years
                    ),
                    rules=self.rules,
                    as_of=as_of,
                ).value.payment_cents
            )
            scenarios.append(
                RateScenarioOut(
                    rate=float(rate),
                    monthly_payment_cents=payment,
                    monthly_ownership_cost_cents=ownership.total_monthly_cents
                    - mortgage.payment_cents
                    + payment,
                    change_cents=payment - mortgage.payment_cents,
                )
            )
        response.rate_scenarios = scenarios

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
            comparable_grid=ComparableGridOut(
                price_per_square_foot_cents=kw["grid"].price_per_square_foot_cents,
                over_adjusted=list(kw["grid"].over_adjusted),
                rows=[
                    AdjustedComparableOut(
                        address=row.scored.comparable.address,
                        sale_price_cents=row.scored.comparable.sale_price_cents,
                        sale_date=row.scored.comparable.sale_date.isoformat(),
                        similarity=float(row.scored.similarity),
                        included=row.scored.included,
                        reason=row.scored.reason,
                        adjustments=[
                            AdjustmentOut(
                                attribute=a.attribute,
                                subject_value=a.subject_value,
                                comparable_value=a.comparable_value,
                                amount_cents=a.amount_cents,
                                basis=a.basis,
                            )
                            for a in row.adjustments
                        ],
                        unadjusted=[
                            UnadjustedAttributeOut(attribute=u.attribute, reason=u.reason)
                            for u in row.unadjusted
                        ],
                        adjusted_price_cents=row.adjusted_price_cents,
                        net_adjustment_cents=row.net_adjustment_cents,
                        gross_adjustment_cents=row.gross_adjustment_cents,
                        gross_adjustment_ratio=float(row.gross_adjustment_ratio),
                    )
                    for row in kw["grid"].rows
                ],
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


def to_domain(
    request: AnalyzeRequest,
) -> tuple[PropertyFinancials, BuyerFinancials, MortgageTerms]:
    """The engines' value objects for a request. Shared with the scenario service."""
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
    return property_, buyer, terms


def _bucket(factors: dict[str, list[FactorOut]], factor: Factor) -> None:
    out = FactorOut(
        component=factor.component.value,
        direction=factor.direction.value,
        magnitude=float(factor.magnitude),
        sentence=factor.sentence,
    )
    factors["positive" if factor.direction.value == "positive" else "negative"].append(out)


def _location(location: LocationFacts | None, max_commute: int | None) -> Any:
    """Build the location subscore, or say precisely why there is not one."""
    if location is None or (location.commute_minutes is None and not location.amenity_counts):
        reason = (
            location.unavailable_reason
            if location and location.unavailable_reason
            else "No location services are configured, so commute and amenities could "
            "not be measured."
        )
        return unavailable(Component.LOCATION, reason)
    return location_subscore(
        commute_minutes=location.commute_minutes,
        max_commute_minutes=max_commute,
        commute_is_estimated=location.commute_is_estimated,
        amenity_counts=location.amenity_counts,
    )


def _cost_name(reason: str) -> str:
    """Turn an unavailable reason into the phrase a user will recognise."""
    lowered = reason.lower()
    if "tax" in lowered:
        return "property tax"
    if "condo" in lowered:
        return "the condo fee"
    return "a cost component"


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


def inputs_hash_for(request: AnalyzeRequest, rule_set: str, model_version: str) -> str:
    """Public name for the fingerprint, used to spot a repeated analysis."""
    return _inputs_hash(request, rule_set, model_version)


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
