"""Five- and ten-year ownership projections for the Deep Dive.

What it costs to own the home for a period, and what might come back on a sale,
under stated assumptions. Two kinds of number live here and are kept apart:

* **Calculated** — mortgage interest, principal and balance, walked month by month
  from the same payment the analysis computed. These follow from the inputs.
* **Assumed** — appreciation, cost growth, selling costs and the return the down
  payment might have earned elsewhere. These are scenarios, never forecasts, and
  a 0% appreciation case is always included so no outcome depends on prices rising.

Pure: value objects in, value objects out.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.money import cents
from app.engines.financial.mortgage import (
    MONTHS_PER_YEAR,
    monthly_periodic_rate,
    payment_for,
    schedule_by_year,
)

RATE_DELTAS = (Decimal("-0.01"), Decimal("0"), Decimal("0.01"), Decimal("0.02"))


@dataclass(frozen=True, slots=True)
class ProjectionAssumptions:
    appreciation_rates: tuple[Decimal, ...]
    selling_cost_rate: Decimal
    opportunity_return_rate: Decimal
    property_tax_growth: Decimal
    condo_fee_growth: Decimal
    insurance_growth: Decimal
    maintenance_growth: Decimal
    utilities_growth: Decimal


@dataclass(frozen=True, slots=True)
class ProjectionInput:
    purchase_price_cents: int
    down_payment_cents: int
    closing_costs_cents: int
    financed_principal_cents: int
    contract_rate: Decimal
    amortization_years: int
    monthly_payment_cents: int
    monthly_property_tax_cents: int
    monthly_insurance_cents: int
    monthly_condo_fee_cents: int
    monthly_utilities_cents: int
    monthly_maintenance_cents: int


@dataclass(frozen=True, slots=True)
class AppreciationOutcome:
    rate: Decimal
    home_value_cents: int
    selling_costs_cents: int
    mortgage_balance_cents: int
    equity_after_sale_cents: int
    net_cost_cents: int
    """Everything paid out, minus what a sale at this value would return."""

    net_cost_with_opportunity_cents: int


@dataclass(frozen=True, slots=True)
class YearRow:
    year: int
    interest_cents: int
    principal_cents: int
    balance_cents: int
    carrying_costs_cents: int
    cumulative_outlay_cents: int


@dataclass(frozen=True, slots=True)
class HorizonProjection:
    years: int
    mortgage_payments_cents: int
    interest_paid_cents: int
    principal_repaid_cents: int
    mortgage_balance_cents: int
    property_tax_cents: int
    insurance_cents: int
    condo_fees_cents: int
    utilities_cents: int
    maintenance_cents: int
    carrying_costs_cents: int
    total_outlay_cents: int
    opportunity_cost_cents: int
    outcomes: tuple[AppreciationOutcome, ...]


@dataclass(frozen=True, slots=True)
class RateSensitivity:
    rate: Decimal
    monthly_payment_cents: int
    change_cents: int
    five_year_interest_cents: int


@dataclass(frozen=True, slots=True)
class Projection:
    horizons: tuple[HorizonProjection, ...]
    yearly: tuple[YearRow, ...]
    rate_sensitivity: tuple[RateSensitivity, ...]


def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _grown_total(monthly_cents: int, growth: Decimal, years: int) -> int:
    """Sum of an annual cost growing at ``growth`` a year, for ``years`` years."""
    annual = Decimal(monthly_cents * MONTHS_PER_YEAR)
    return _round(sum((annual * (Decimal(1) + growth) ** y for y in range(years)), Decimal(0)))


def project(
    facts: ProjectionInput, assumptions: ProjectionAssumptions, horizons: tuple[int, ...] = (5, 10)
) -> Projection:
    periodic = monthly_periodic_rate(facts.contract_rate)
    longest = max(horizons)
    schedule = schedule_by_year(
        cents(facts.financed_principal_cents), periodic, cents(facts.monthly_payment_cents), longest
    )

    def carrying(years: int) -> dict[str, int]:
        return {
            "tax": _grown_total(
                facts.monthly_property_tax_cents, assumptions.property_tax_growth, years
            ),
            "insurance": _grown_total(
                facts.monthly_insurance_cents, assumptions.insurance_growth, years
            ),
            "condo": _grown_total(
                facts.monthly_condo_fee_cents, assumptions.condo_fee_growth, years
            ),
            "utilities": _grown_total(
                facts.monthly_utilities_cents, assumptions.utilities_growth, years
            ),
            "maintenance": _grown_total(
                facts.monthly_maintenance_cents, assumptions.maintenance_growth, years
            ),
        }

    upfront = facts.down_payment_cents + facts.closing_costs_cents
    yearly: list[YearRow] = []
    for index, (year_interest, year_principal, year_balance) in enumerate(schedule, start=1):
        costs = carrying(index)
        paid = sum(i + p for i, p, _ in schedule[:index])
        yearly.append(
            YearRow(
                year=index,
                interest_cents=year_interest,
                principal_cents=year_principal,
                balance_cents=year_balance,
                carrying_costs_cents=sum(costs.values()) - sum(carrying(index - 1).values()),
                cumulative_outlay_cents=upfront + paid + sum(costs.values()),
            )
        )

    results: list[HorizonProjection] = []
    for years in horizons:
        rows = schedule[:years]
        interest = sum(r[0] for r in rows)
        principal = sum(r[1] for r in rows)
        balance: int = rows[-1][2] if rows else facts.financed_principal_cents
        costs = carrying(years)
        carrying_total = sum(costs.values())
        payments = interest + principal
        outlay = upfront + payments + carrying_total
        opportunity = _round(
            Decimal(upfront) * ((Decimal(1) + assumptions.opportunity_return_rate) ** years - 1)
        )
        outcomes = []
        for rate in assumptions.appreciation_rates:
            value = _round(Decimal(facts.purchase_price_cents) * (Decimal(1) + rate) ** years)
            selling = _round(Decimal(value) * assumptions.selling_cost_rate)
            equity = value - selling - balance
            outcomes.append(
                AppreciationOutcome(
                    rate=rate,
                    home_value_cents=value,
                    selling_costs_cents=selling,
                    mortgage_balance_cents=balance,
                    equity_after_sale_cents=equity,
                    net_cost_cents=outlay - equity,
                    net_cost_with_opportunity_cents=outlay - equity + opportunity,
                )
            )
        results.append(
            HorizonProjection(
                years=years,
                mortgage_payments_cents=payments,
                interest_paid_cents=interest,
                principal_repaid_cents=principal,
                mortgage_balance_cents=balance,
                property_tax_cents=costs["tax"],
                insurance_cents=costs["insurance"],
                condo_fees_cents=costs["condo"],
                utilities_cents=costs["utilities"],
                maintenance_cents=costs["maintenance"],
                carrying_costs_cents=carrying_total,
                total_outlay_cents=outlay,
                opportunity_cost_cents=opportunity,
                outcomes=tuple(outcomes),
            )
        )

    sensitivity = []
    periods = facts.amortization_years * MONTHS_PER_YEAR
    for delta in RATE_DELTAS:
        rate = facts.contract_rate + delta
        if rate <= 0:
            continue
        i = monthly_periodic_rate(rate)
        payment = (
            payment_for(cents(facts.financed_principal_cents), i, periods)
            if delta
            else (facts.monthly_payment_cents)
        )
        five = schedule_by_year(cents(facts.financed_principal_cents), i, cents(payment), 5)
        sensitivity.append(
            RateSensitivity(
                rate=rate,
                monthly_payment_cents=payment,
                change_cents=payment - facts.monthly_payment_cents,
                five_year_interest_cents=sum(r[0] for r in five),
            )
        )

    return Projection(
        horizons=tuple(results), yearly=tuple(yearly), rate_sensitivity=tuple(sensitivity)
    )
