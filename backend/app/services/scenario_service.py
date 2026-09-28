"""Offer scenarios, down-payment scenarios and the Deep Dive report.

Every figure here is re-derived from the request the user originally submitted,
through the same financial engine as the analysis itself. Nothing is scaled,
interpolated or approximated from a previous result: a scenario at $875,000 is a
full calculation at $875,000, land transfer tax brackets and CMHC bands included.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from app.billing.config import ProjectionConfig
from app.core.money import cents
from app.engines.base import EngineResult
from app.engines.financial.contracts import (
    AffordabilityResult,
    ClosingCostResult,
    MortgageResult,
    MortgageTerms,
    OwnershipCostResult,
    PropertyKind,
    QualificationEstimate,
)
from app.engines.financial.mortgage import (
    minimum_down_payment,
    monthly_periodic_rate,
    schedule_by_year,
)
from app.engines.scenarios.projection import (
    ProjectionAssumptions,
    ProjectionInput,
    project,
)
from app.schemas.analysis import AnalyzeRequest
from app.services.analysis_service import AnalysisService, to_domain

DownPaymentMode = Literal["same_amount", "same_percent"]

STANDARD_QUESTIONS = (
    "Have there been any offers, and is the seller holding offers until a set date?",
    "What is included in the sale (appliances, fixtures, window coverings)?",
    "Are any major systems (furnace, AC, water heater) rented rather than owned?",
    "Has the property had water in the basement, insurance claims or pest issues?",
    "Are there any open building permits or unpermitted additions?",
    "What were the utility costs over the last twelve months?",
)


@dataclass(frozen=True, slots=True)
class MoneySnapshot:
    mortgage: MortgageResult
    closing: ClosingCostResult
    ownership: OwnershipCostResult
    affordability: AffordabilityResult
    qualification: QualificationEstimate


class ScenarioService:
    def __init__(self, analysis: AnalysisService) -> None:
        self.analysis = analysis
        self.financial = analysis.financial
        self.rules = analysis.rules

    def money_at(
        self,
        request: AnalyzeRequest,
        *,
        as_of: date,
        price_cents: int | None = None,
        down_payment_cents: int | None = None,
        contract_rate: Decimal | None = None,
    ) -> MoneySnapshot:
        """The full money calculation with any of price, down payment or rate replaced."""
        property_, buyer, terms = to_domain(request)
        if price_cents is not None:
            property_ = dataclasses.replace(property_, purchase_price_cents=cents(price_cents))
        if down_payment_cents is not None:
            buyer = dataclasses.replace(buyer, down_payment_cents=cents(down_payment_cents))
        if contract_rate is not None:
            terms = MortgageTerms(
                contract_rate=contract_rate, amortization_years=terms.amortization_years
            )

        def value[T](result: EngineResult[T]) -> T:
            return result.value

        mortgage = value(
            self.financial.mortgage(
                property_=property_, buyer=buyer, terms=terms, rules=self.rules, as_of=as_of
            )
        )
        closing = value(
            self.financial.closing_costs(
                property_=property_, buyer=buyer, mortgage=mortgage, rules=self.rules, as_of=as_of
            )
        )
        ownership = value(
            self.financial.ownership_cost(
                property_=property_, mortgage=mortgage, rules=self.rules, as_of=as_of
            )
        )
        qualification = value(
            self.financial.qualification(
                property_=property_,
                buyer=buyer,
                terms=terms,
                ownership=ownership,
                rules=self.rules,
                as_of=as_of,
            )
        )
        affordability = value(
            self.financial.affordability(
                buyer=buyer, ownership=ownership, closing=closing, mortgage=mortgage
            )
        )
        return MoneySnapshot(mortgage, closing, ownership, affordability, qualification)

    # --- offers ------------------------------------------------------------------

    def offers(
        self,
        request: AnalyzeRequest,
        prices_cents: list[int],
        *,
        mode: DownPaymentMode,
        as_of: date,
    ) -> list[dict[str, Any]]:
        """The financial consequences of each possible offer. Never a recommendation."""
        asking = request.property.purchase_price_cents
        down = request.buyer.down_payment_cents
        down_share = Decimal(down) / Decimal(asking)
        rows: list[dict[str, Any]] = []
        for price in prices_cents:
            this_down = down if mode == "same_amount" else int(Decimal(price) * down_share)
            minimum = minimum_down_payment(cents(price), self.rules, as_of=as_of)
            row: dict[str, Any] = {
                "price_cents": price,
                "difference_from_asking_cents": price - asking,
                "down_payment_cents": this_down,
                "minimum_down_payment_cents": minimum,
            }
            if this_down < minimum:
                row["error"] = (
                    f"A down payment of ${this_down // 100:,} is below the ${minimum // 100:,} "
                    "minimum for this price."
                )
                rows.append(row)
                continue
            if this_down >= price:
                row["error"] = "The down payment covers the whole price."
                rows.append(row)
                continue
            try:
                money = self.money_at(
                    request, as_of=as_of, price_cents=price, down_payment_cents=this_down
                )
            except ValueError as exc:
                row["error"] = str(exc)
                rows.append(row)
                continue
            sensitivity = []
            for delta in (Decimal("0.01"), Decimal("0.02")):
                shifted = self.money_at(
                    request,
                    as_of=as_of,
                    price_cents=price,
                    down_payment_cents=this_down,
                    contract_rate=request.terms.contract_rate + delta,
                )
                sensitivity.append(
                    {
                        "rate": float(request.terms.contract_rate + delta),
                        "monthly_payment_cents": shifted.mortgage.payment_cents,
                        "monthly_carrying_cost_cents": shifted.ownership.total_monthly_cents,
                    }
                )
            row.update(
                {
                    "mortgage_principal_cents": money.mortgage.principal_cents,
                    "insurance_premium_cents": money.mortgage.insurance_premium_cents,
                    "monthly_payment_cents": money.mortgage.payment_cents,
                    "closing_costs_cents": money.closing.total_cents,
                    "cash_required_cents": money.affordability.cash_required_cents,
                    "cash_shortfall_cents": money.affordability.cash_shortfall_cents,
                    "monthly_carrying_cost_cents": money.ownership.total_monthly_cents,
                    "gds": float(money.qualification.gds),
                    "tds": float(money.qualification.tds),
                    "may_qualify": money.qualification.may_qualify,
                    "rate_sensitivity": sensitivity,
                }
            )
            rows.append(row)
        return rows

    # --- down payment scenarios -----------------------------------------------------

    def down_payment_scenarios(
        self, request: AnalyzeRequest, *, as_of: date
    ) -> list[dict[str, Any]]:
        price = request.property.purchase_price_cents
        minimum = minimum_down_payment(cents(price), self.rules, as_of=as_of)
        candidates = {
            "Minimum allowed": minimum,
            "10%": price // 10,
            "20%": price // 5,
            "Your down payment": request.buyer.down_payment_cents,
        }
        seen: set[int] = set()
        rows: list[dict[str, Any]] = []
        for label, amount in sorted(candidates.items(), key=lambda kv: kv[1]):
            if amount < minimum or amount >= price or amount in seen:
                continue
            seen.add(amount)
            money = self.money_at(request, as_of=as_of, down_payment_cents=amount)
            periodic = monthly_periodic_rate(request.terms.contract_rate)
            five = schedule_by_year(
                money.mortgage.principal_cents, periodic, money.mortgage.payment_cents, 5
            )
            rows.append(
                {
                    "label": label,
                    "is_yours": amount == request.buyer.down_payment_cents,
                    "down_payment_cents": amount,
                    "down_payment_share": float(Decimal(amount) / Decimal(price)),
                    "insurance_premium_cents": money.mortgage.insurance_premium_cents,
                    "mortgage_principal_cents": money.mortgage.principal_cents,
                    "monthly_payment_cents": money.mortgage.payment_cents,
                    "monthly_carrying_cost_cents": money.ownership.total_monthly_cents,
                    "cash_required_cents": money.affordability.cash_required_cents,
                    "five_year_interest_cents": sum(r[0] for r in five),
                }
            )
        return rows

    # --- deep dive ---------------------------------------------------------------------

    def deep_dive(
        self,
        request: AnalyzeRequest,
        stored: dict[str, Any],
        config: ProjectionConfig,
        *,
        as_of: date,
    ) -> dict[str, Any]:
        money = self.money_at(request, as_of=as_of)
        assumptions = ProjectionAssumptions(
            appreciation_rates=tuple(config.appreciation_rates),
            selling_cost_rate=config.selling_cost_rate,
            opportunity_return_rate=config.opportunity_return_rate,
            property_tax_growth=config.property_tax_growth,
            condo_fee_growth=config.condo_fee_growth,
            insurance_growth=config.insurance_growth,
            maintenance_growth=config.maintenance_growth,
            utilities_growth=config.utilities_growth,
        )
        projection = project(
            ProjectionInput(
                purchase_price_cents=request.property.purchase_price_cents,
                down_payment_cents=request.buyer.down_payment_cents,
                closing_costs_cents=money.closing.total_cents,
                financed_principal_cents=money.mortgage.principal_cents,
                contract_rate=request.terms.contract_rate,
                amortization_years=request.terms.amortization_years,
                monthly_payment_cents=money.mortgage.payment_cents,
                monthly_property_tax_cents=money.ownership.property_tax_cents,
                monthly_insurance_cents=money.ownership.insurance_cents,
                monthly_condo_fee_cents=money.ownership.condo_fee_cents,
                monthly_utilities_cents=money.ownership.utilities_cents,
                monthly_maintenance_cents=money.ownership.maintenance_reserve_cents,
            ),
            assumptions,
        )
        is_condo = PropertyKind(request.property.property_kind) in (
            PropertyKind.CONDO_APARTMENT,
            PropertyKind.CONDO_TOWNHOUSE,
        )
        ten = next(h for h in projection.horizons if h.years == 10)
        tax_supplied = request.property.annual_property_tax_cents is not None
        fee_supplied = request.property.monthly_condo_fee_cents is not None

        missing = stored.get("missing_info", [])
        questions = [item["what_to_ask_for"] for item in missing] + list(STANDARD_QUESTIONS)

        return {
            "title": _title(request),
            "as_of": as_of.isoformat(),
            "summary": {
                "purchase_price_cents": request.property.purchase_price_cents,
                "down_payment_cents": request.buyer.down_payment_cents,
                "mortgage_principal_cents": money.mortgage.principal_cents,
                "insurance_premium_cents": money.mortgage.insurance_premium_cents,
                "monthly_payment_cents": money.mortgage.payment_cents,
                "monthly_carrying_cost_cents": money.ownership.total_monthly_cents,
                "closing_costs_cents": money.closing.total_cents,
                "cash_required_cents": money.affordability.cash_required_cents,
                "contract_rate": float(request.terms.contract_rate),
                "amortization_years": request.terms.amortization_years,
            },
            "projection": {
                "horizons": [dataclasses.asdict(h) for h in projection.horizons],
                "yearly": [dataclasses.asdict(y) for y in projection.yearly],
            },
            "rate_sensitivity": [dataclasses.asdict(r) for r in projection.rate_sensitivity],
            "down_payment_scenarios": self.down_payment_scenarios(request, as_of=as_of),
            "closing_costs": {
                "lines": [
                    {
                        "key": line.key,
                        "label": line.label,
                        "amount_cents": line.amount_cents,
                        "basis": "estimated" if line.is_estimate else "known",
                    }
                    for line in money.closing.lines
                ],
                "rebates_cents": money.closing.rebates_cents,
                "total_cents": money.closing.total_cents,
            },
            "opportunity_cost": {
                "upfront_cents": request.buyer.down_payment_cents + money.closing.total_cents,
                "assumed_return": float(config.opportunity_return_rate),
                "five_year_cents": projection.horizons[0].opportunity_cost_cents,
                "ten_year_cents": ten.opportunity_cost_cents,
                "note": "What the down payment and closing costs might have earned if invested "
                f"instead, at an assumed {pct(config.opportunity_return_rate)} a year. An "
                "assumption, not a forecast.",
            },
            "property_tax": {
                "monthly_cents": money.ownership.property_tax_cents,
                "ten_year_cents": ten.property_tax_cents,
                "basis": "user_provided"
                if tax_supplied
                else ("estimated" if money.ownership.property_tax_cents else "unavailable"),
                "growth": float(config.property_tax_growth),
            },
            "condo_fee": {
                "applies": is_condo,
                "monthly_cents": money.ownership.condo_fee_cents,
                "ten_year_cents": ten.condo_fees_cents,
                "basis": "user_provided" if fee_supplied else "unavailable",
                "growth": float(config.condo_fee_growth),
            },
            "insurance": {
                "monthly_cents": money.ownership.insurance_cents,
                "ten_year_cents": ten.insurance_cents,
                "basis": "assumption",
                "growth": float(config.insurance_growth),
                "note": "A planning default for an Ontario policy. Get a quote for this address.",
            },
            "maintenance": {
                "monthly_cents": money.ownership.maintenance_reserve_cents,
                "ten_year_cents": ten.maintenance_cents,
                "basis": "assumption",
                "growth": float(config.maintenance_growth),
                "note": "A reserve for repairs set as a share of price. Older homes and "
                "deferred maintenance can need much more.",
            },
            "cash_flow": {
                "monthly_breakdown": stored.get("monthly_breakdown", []),
                "personal": stored.get("personal"),
            },
            "risk": {
                "qualification": stored.get("qualification"),
                "risks": stored.get("risks", []),
                "negative_factors": stored.get("factors", {}).get("negative", []),
            },
            "missing_info": missing,
            "questions": questions,
            "assumptions": [
                {
                    "key": "appreciation_rates",
                    "label": "Appreciation scenarios",
                    "value": ", ".join(pct(r) for r in config.appreciation_rates) + " a year",
                    "basis": "assumption",
                },
                {
                    "key": "selling_cost_rate",
                    "label": "Selling costs on resale (commission, legal)",
                    "value": pct(config.selling_cost_rate) + " of sale price",
                    "basis": "assumption",
                },
                {
                    "key": "opportunity_return_rate",
                    "label": "Return the upfront cash might earn elsewhere",
                    "value": pct(config.opportunity_return_rate) + " a year",
                    "basis": "assumption",
                },
                {
                    "key": "cost_growth",
                    "label": "Annual growth: tax / condo fee / insurance / maintenance / utilities",
                    "value": " / ".join(
                        pct(g)
                        for g in (
                            config.property_tax_growth,
                            config.condo_fee_growth,
                            config.insurance_growth,
                            config.maintenance_growth,
                            config.utilities_growth,
                        )
                    ),
                    "basis": "assumption",
                },
                {
                    "key": "rate_constant",
                    "label": "Mortgage rate",
                    "value": f"{pct(request.terms.contract_rate)} held for the whole projection",
                    "basis": "assumption",
                },
            ]
            + [
                {
                    "key": a["key"],
                    "label": a["key"].replace("_", " "),
                    "value": str(a["value"]),
                    "basis": "assumption",
                    "rationale": a.get("rationale", ""),
                }
                for a in stored.get("assumptions", [])
            ],
            "notes": [
                "The mortgage rate is held constant. Real renewals happen every term (often "
                "five years) at whatever rates are then; see the rate sensitivity table.",
                "Appreciation scenarios are illustrations, not predictions. The 0% case "
                "shows the outcome if prices do not rise at all.",
                "Net cost is everything paid out, minus the equity a sale at that value "
                "would return after selling costs and the remaining mortgage.",
            ],
        }


def pct(value: Decimal | float) -> str:
    return f"{Decimal(str(value)) * 100:.1f}%"


def _title(request: AnalyzeRequest) -> str:
    if request.property.address:
        return request.property.address
    kind = request.property.property_kind.replace("_", " ")
    return f"{kind.capitalize()} at ${request.property.purchase_price_cents // 100:,}"


def title_for(request: AnalyzeRequest) -> str:
    return _title(request)
