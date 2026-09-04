"""The qualification estimate — deliberately a different question from affordability.

A lender asks: at the stress-tested rate, do the ratios clear the published limits?
A household asks: can we live like this? Those answers diverge routinely, and the
gap is where people get hurt, so the two live in different types and are never
merged into one reassuring number.

Note what the stress test does and does not touch. The **payment** is recomputed at
the minimum qualifying rate — the greater of 5.25% and contract plus 2% — while
taxes, heat and condo fees stay as they are. Stressing the whole ownership cost
would be a different and much harsher test than the one lenders actually apply.

Nothing here approves anything. :class:`QualificationEstimate` carries its own
disclaimer field so the caveat travels with the number into the API payload rather
than living in a footer someone can restyle away.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.money import Cents, cents
from app.engines.base import EngineResult, TraceBuilder
from app.engines.financial.contracts import (
    BuyerFinancials,
    MortgageTerms,
    OwnershipCostResult,
    PropertyFinancials,
    PropertyKind,
    QualificationEstimate,
)
from app.engines.financial.mortgage import (
    MONTHS_PER_YEAR,
    minimum_down_payment,
    monthly_periodic_rate,
    payment_for,
    premium_rate_for,
)
from app.engines.rules import RuleSet

_CONDOS = {PropertyKind.CONDO_APARTMENT, PropertyKind.CONDO_TOWNHOUSE}


def stressed_rate(contract_rate: Decimal, rules: RuleSet, *, as_of: date) -> Decimal:
    """The minimum qualifying rate: greater of the floor and contract plus the buffer."""
    rule = rules.get("CA", "mqr.floor", as_of=as_of)
    floor = Decimal(str(rule.value["rate"]))
    buffer_ = Decimal(str(rule.value["buffer"]))
    return max(floor, contract_rate + buffer_)


def _heat_floor(kind: PropertyKind, rules: RuleSet, *, as_of: date) -> Cents:
    value = rules.get("CA", "qualification.heat_floor_cents", as_of=as_of).value
    return cents(int(value["condo" if kind in _CONDOS else "house"]))


def compute_qualification(
    *,
    property_: PropertyFinancials,
    buyer: BuyerFinancials,
    terms: MortgageTerms,
    ownership: OwnershipCostResult,
    rules: RuleSet,
    as_of: date,
) -> EngineResult[QualificationEstimate]:
    trace = TraceBuilder()
    limits = rules.get("CA", "qualification.debt_service_limits", as_of=as_of).value
    gds_limit = Decimal(str(limits["gds"]))
    tds_limit = Decimal(str(limits["tds"]))

    mqr = trace.step(
        "minimum qualifying rate",
        "max(floor, contract_rate + buffer)",
        {"contract_rate": str(terms.contract_rate)},
        stressed_rate(terms.contract_rate, rules, as_of=as_of),
        rule_keys=("CA/mqr.floor",),
    )

    principal = cents(property_.purchase_price_cents - buyer.down_payment_cents)
    stressed_payment = trace.step(
        "stressed payment",
        "payment recomputed at the qualifying rate, same amortization",
        {"principal_cents": principal, "mqr": str(mqr), "years": terms.amortization_years},
        payment_for(
            principal,
            monthly_periodic_rate(mqr, compounding_per_year=terms.compounding_per_year),
            terms.amortization_years * MONTHS_PER_YEAR,
        ),
        unit="cents",
    )

    heat = _heat_floor(property_.property_kind, rules, as_of=as_of)
    condo_share = Decimal(
        str(
            rules.get("CA", "qualification.heat_floor_cents", as_of=as_of).value[
                "condo_fee_inclusion"
            ]
        )
    )
    condo_component = cents(int(Decimal(ownership.condo_fee_cents) * condo_share))

    housing_costs = trace.step(
        "qualifying housing costs",
        "stressed_payment + property_tax/12 + heat + 50% of condo fee",
        {
            "stressed_payment_cents": stressed_payment,
            "property_tax_cents": ownership.property_tax_cents,
            "heat_cents": heat,
            "condo_component_cents": condo_component,
        },
        cents(stressed_payment + ownership.property_tax_cents + heat + condo_component),
        unit="cents",
        rule_keys=("CA/qualification.heat_floor_cents",),
    )

    income = max(buyer.household_income_cents, buyer.gross_annual_income_cents)
    monthly_income = Decimal(income) / 12
    if monthly_income <= 0:
        raise ValueError("household income must be positive to estimate qualification")

    gds = trace.step(
        "gross debt service",
        "qualifying_housing_costs / gross_monthly_income",
        {"housing_cents": housing_costs, "monthly_income_cents": int(monthly_income)},
        (Decimal(housing_costs) / monthly_income).quantize(Decimal("0.0001")),
    )
    tds = trace.step(
        "total debt service",
        "(qualifying_housing_costs + monthly_debts) / gross_monthly_income",
        {"housing_cents": housing_costs, "debts_cents": buyer.monthly_debt_payments_cents},
        (Decimal(housing_costs + buyer.monthly_debt_payments_cents) / monthly_income).quantize(
            Decimal("0.0001")
        ),
    )

    blocking: list[str] = []
    if gds > gds_limit:
        blocking.append(f"Gross debt service {gds:.1%} exceeds the {gds_limit:.0%} guideline.")
    if tds > tds_limit:
        blocking.append(f"Total debt service {tds:.1%} exceeds the {tds_limit:.0%} guideline.")

    minimum = minimum_down_payment(property_.purchase_price_cents, rules, as_of=as_of)
    if buyer.down_payment_cents < minimum:
        blocking.append(f"Down payment is below the ${minimum / 100:,.0f} minimum for this price.")

    insured_cap = cents(
        int(rules.get("CA", "insured.max_price_cents", as_of=as_of).value["amount_cents"])
    )
    ltv = Decimal(principal) / Decimal(property_.purchase_price_cents)
    insured_eligible = property_.purchase_price_cents <= insured_cap and ltv > Decimal("0.80")

    amortization_rule = rules.get("CA", "insured.max_amortization_years", as_of=as_of)
    long_amortization = terms.amortization_years > int(amortization_rule.value["standard"])
    if (
        insured_eligible
        and long_amortization
        and not (buyer.first_time_buyer or property_.is_new_build)
    ):
        blocking.append(
            "A 30-year amortization on an insured mortgage requires a first-time "
            "buyer or a new build."
        )

    max_price = _max_supported_price(
        property_=property_,
        buyer=buyer,
        terms=terms,
        rules=rules,
        as_of=as_of,
        gds_limit=gds_limit,
        tds_limit=tds_limit,
        heat=heat,
        condo_component=condo_component,
        monthly_income=monthly_income,
    )
    trace.step(
        "maximum supported price",
        "bisection on price until GDS or TDS reaches its limit",
        {"gds_limit": str(gds_limit), "tds_limit": str(tds_limit)},
        max_price,
        unit="cents",
    )

    estimate = QualificationEstimate(
        may_qualify=not blocking,
        stressed_rate=mqr,
        gds=gds,
        tds=tds,
        gds_limit=gds_limit,
        tds_limit=tds_limit,
        insured_eligible=insured_eligible,
        max_purchase_price_cents=max_price,
        blocking_reasons=tuple(blocking),
    )
    return trace.finish(estimate)


def _max_supported_price(
    *,
    property_: PropertyFinancials,
    buyer: BuyerFinancials,
    terms: MortgageTerms,
    rules: RuleSet,
    as_of: date,
    gds_limit: Decimal,
    tds_limit: Decimal,
    heat: Cents,
    condo_component: Cents,
    monthly_income: Decimal,
) -> Cents | None:
    """Largest price whose stressed ratios still clear both limits, by bisection.

    Bisection rather than algebra because the constraint is not smooth: the
    down-payment minimum steps at $500k, insurance eligibility falls off a cliff at
    $1.5M, and the premium rate jumps between loan-to-value bands. A closed form
    would have to special-case every one of those, and would be wrong at exactly the
    boundaries that matter.

    Deterministic: fixed iteration count, fixed tolerance, no convergence loop that
    could vary between runs.
    """
    tax_rate_rule = rules.find(property_.jurisdiction, "property_tax.residential_rate", as_of=as_of)
    if tax_rate_rule is None:
        return None
    tax_rate = Decimal(str(tax_rate_rule.value["rate"]))
    periodic = monthly_periodic_rate(
        stressed_rate(terms.contract_rate, rules, as_of=as_of),
        compounding_per_year=terms.compounding_per_year,
    )
    periods = terms.amortization_years * MONTHS_PER_YEAR

    def clears(price_cents: int) -> bool:
        price = cents(price_cents)
        if buyer.down_payment_cents < minimum_down_payment(price, rules, as_of=as_of):
            return False
        principal = price - buyer.down_payment_cents
        if principal <= 0:
            return True
        ltv = Decimal(principal) / Decimal(price)
        if ltv > Decimal("0.95"):
            return False
        insured_cap = int(
            rules.get("CA", "insured.max_price_cents", as_of=as_of).value["amount_cents"]
        )
        financed = principal
        if price <= insured_cap and ltv > Decimal("0.80"):
            financed += int(Decimal(principal) * premium_rate_for(ltv, rules, as_of=as_of))
        payment = payment_for(cents(financed), periodic, periods)
        monthly_tax = int(Decimal(price) * tax_rate / 12)
        housing = payment + monthly_tax + heat + condo_component
        gds = Decimal(housing) / monthly_income
        tds = Decimal(housing + buyer.monthly_debt_payments_cents) / monthly_income
        return gds <= gds_limit and tds <= tds_limit

    low, high = 0, 500_000_000  # $5M ceiling on the search
    if not clears(low + 100_00):
        return cents(0)
    for _ in range(40):  # 40 halvings of $5M resolves well below a dollar
        mid = (low + high) // 2
        if clears(mid):
            low = mid
        else:
            high = mid
    return cents(low - low % 100)  # round down to the dollar
