"""Monthly ownership cost, and the affordability ratios built on it.

The number nobody assembles until after closing:

    mortgage + property tax/12 + insurance/12 + condo fees + utilities
      + maintenance reserve = monthly ownership cost

Three of those five are estimates when the user has not supplied them, and each
one enters as a visible assumption rather than a silent default. Understating this
figure is how a household ends up house-poor while every calculator they used said
they were fine.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.money import apply_rate, cents
from app.engines.base import EngineResult, TraceBuilder
from app.engines.financial.contracts import (
    AffordabilityResult,
    BuyerFinancials,
    ClosingCostResult,
    MortgageResult,
    OwnershipCostResult,
    PropertyFinancials,
    PropertyKind,
)
from app.engines.rules import RuleSet
from app.provenance.types import Fact

_CONDOS = {PropertyKind.CONDO_APARTMENT, PropertyKind.CONDO_TOWNHOUSE}


def compute_ownership_cost(
    *,
    property_: PropertyFinancials,
    mortgage: MortgageResult,
    rules: RuleSet,
    as_of: date,
) -> EngineResult[OwnershipCostResult]:
    trace = TraceBuilder()
    defaults = rules.get("ON", "ownership.defaults", as_of=as_of).value
    is_condo = property_.property_kind in _CONDOS

    # Property tax: the user's figure if they have one, otherwise the municipal rate
    # applied to price. MPAC values are frozen at a 2016 valuation date, so price is
    # a rough proxy and the result is an estimate that says so.
    if property_.annual_property_tax_cents is not None:
        annual_tax = property_.annual_property_tax_cents
        trace.step(
            "property tax",
            "as supplied by the user",
            {"annual_cents": annual_tax},
            annual_tax,
            unit="cents",
        )
    else:
        rate_rule = rules.find(property_.jurisdiction, "property_tax.residential_rate", as_of=as_of)
        if rate_rule is None:
            # Only the pilot municipality's rate is seeded, and a rate is not
            # something to guess — they range from about 0.6% to over 1.8% across
            # Ontario, which is thousands of dollars a year on the same house. The
            # cost comes back without it, saying so, rather than quietly understated
            # by a made-up number.
            annual_tax = cents(0)
            trace.missing(
                Fact.unavailable(
                    f"No published residential tax rate for {property_.jurisdiction}. "
                    "The monthly cost below excludes property tax — enter the figure "
                    "from the listing to complete it."
                )
            )
        else:
            rate = Decimal(str(rate_rule.value["rate"]))
            annual_tax = trace.step(
                "property tax",
                "purchase_price * municipal_residential_rate",
                {"purchase_price_cents": property_.purchase_price_cents, "rate": str(rate)},
                apply_rate(property_.purchase_price_cents, rate),
                unit="cents",
                rule_keys=(f"{rate_rule.jurisdiction}/property_tax.residential_rate",),
            )
            trace.assume(
                "property_tax_basis",
                "purchase price",
                "Estimated from the municipal rate applied to purchase price. "
                "Assessments are frozen at a 2016 valuation date, so the real bill is "
                "usually lower.",
                source_key="src_toronto_open_data",
            )

    insurance_annual = cents(
        int(defaults["condo_insurance_annual_cents" if is_condo else "home_insurance_annual_cents"])
    )
    trace.assume(
        "home_insurance",
        insurance_annual,
        "Planning default for an Ontario policy. Replace it with your quote.",
    )

    condo_fee = property_.monthly_condo_fee_cents or cents(0)
    if is_condo and property_.monthly_condo_fee_cents is None:
        # A condo fee depends on the building, not the price, so there is nothing
        # honest to estimate it from. It stays unavailable and the total says so.
        trace.missing(
            Fact.unavailable("No condo fee supplied; it depends on the building, not the price.")
        )

    utilities = cents(
        int(
            defaults[
                "utilities_monthly_condo_cents" if is_condo else "utilities_monthly_house_cents"
            ]
        )
    )
    trace.assume("utilities", utilities, "Planning default; varies with the building and season.")

    reserve_rate = Decimal(
        str(defaults["maintenance_reserve_rate_condo" if is_condo else "maintenance_reserve_rate"])
    )
    maintenance = trace.step(
        "maintenance reserve",
        "purchase_price * reserve_rate / 12",
        {"purchase_price_cents": property_.purchase_price_cents, "rate": str(reserve_rate)},
        cents(apply_rate(property_.purchase_price_cents, reserve_rate) // 12),
        unit="cents",
        rule_keys=("ON/ownership.defaults",),
    )
    trace.assume(
        "maintenance_reserve",
        str(reserve_rate),
        "A freehold sets aside about 1% of value a year; a condo less, because the "
        "fee already funds the building's reserve.",
    )

    monthly_tax = cents(annual_tax // 12)
    monthly_insurance = cents(insurance_annual // 12)
    total = trace.step(
        "monthly ownership cost",
        "mortgage + tax/12 + insurance/12 + condo_fee + utilities + maintenance",
        {
            "mortgage_cents": mortgage.payment_cents,
            "tax_cents": monthly_tax,
            "insurance_cents": monthly_insurance,
            "condo_fee_cents": condo_fee,
            "utilities_cents": utilities,
            "maintenance_cents": maintenance,
        },
        cents(
            mortgage.payment_cents
            + monthly_tax
            + monthly_insurance
            + condo_fee
            + utilities
            + maintenance
        ),
        unit="cents",
    )

    return trace.finish(
        OwnershipCostResult(
            mortgage_payment_cents=mortgage.payment_cents,
            property_tax_cents=monthly_tax,
            insurance_cents=monthly_insurance,
            condo_fee_cents=condo_fee,
            utilities_cents=utilities,
            maintenance_reserve_cents=maintenance,
            total_monthly_cents=total,
        )
    )


def compute_affordability(
    *,
    buyer: BuyerFinancials,
    ownership: OwnershipCostResult,
    closing: ClosingCostResult,
    mortgage: MortgageResult,
) -> EngineResult[AffordabilityResult]:
    """What it costs against what this household has. Not what a lender will approve."""
    trace = TraceBuilder()
    income = max(buyer.household_income_cents, buyer.gross_annual_income_cents)
    monthly_income = Decimal(income) / 12

    if monthly_income <= 0:
        raise ValueError("household income must be positive to compute affordability")

    housing_ratio = trace.step(
        "housing ratio",
        "monthly_ownership_cost / gross_monthly_income",
        {
            "ownership_cents": ownership.total_monthly_cents,
            "monthly_income_cents": int(monthly_income),
        },
        (Decimal(ownership.total_monthly_cents) / monthly_income).quantize(Decimal("0.0001")),
    )
    total_debt_ratio = trace.step(
        "total debt ratio",
        "(monthly_ownership_cost + monthly_debts) / gross_monthly_income",
        {
            "ownership_cents": ownership.total_monthly_cents,
            "debts_cents": buyer.monthly_debt_payments_cents,
        },
        (
            Decimal(ownership.total_monthly_cents + buyer.monthly_debt_payments_cents)
            / monthly_income
        ).quantize(Decimal("0.0001")),
    )

    budget_ratio = None
    if buyer.desired_max_monthly_cents:
        budget_ratio = trace.step(
            "budget adherence",
            "monthly_ownership_cost / stated_maximum",
            {
                "ownership_cents": ownership.total_monthly_cents,
                "budget_cents": buyer.desired_max_monthly_cents,
            },
            (
                Decimal(ownership.total_monthly_cents) / Decimal(buyer.desired_max_monthly_cents)
            ).quantize(Decimal("0.0001")),
        )

    cash_required = trace.step(
        "cash required to close",
        "down_payment + closing_costs",
        {"down_payment_cents": buyer.down_payment_cents, "closing_cents": closing.total_cents},
        cents(buyer.down_payment_cents + closing.total_cents),
        unit="cents",
    )
    shortfall = trace.step(
        "cash shortfall",
        "max(0, cash_required - available_savings)",
        {"cash_required_cents": cash_required, "savings_cents": buyer.available_savings_cents},
        cents(max(0, cash_required - buyer.available_savings_cents)),
        unit="cents",
    )

    # Reserve months measure what is left after closing, not what was there before —
    # the distinction that separates "comfortable" from "cleaned out on possession day".
    remaining = max(0, buyer.available_savings_cents - cash_required) + buyer.emergency_fund_cents
    reserve_months = trace.step(
        "reserve months",
        "(savings_after_closing + emergency_fund) / monthly_ownership_cost",
        {"remaining_cents": remaining, "ownership_cents": ownership.total_monthly_cents},
        (Decimal(remaining) / Decimal(ownership.total_monthly_cents)).quantize(Decimal("0.01"))
        if ownership.total_monthly_cents
        else Decimal(0),
    )

    return trace.finish(
        AffordabilityResult(
            housing_ratio=housing_ratio,
            total_debt_ratio=total_debt_ratio,
            budget_ratio=budget_ratio,
            reserve_months=reserve_months,
            cash_required_cents=cash_required,
            cash_shortfall_cents=shortfall,
        )
    )
