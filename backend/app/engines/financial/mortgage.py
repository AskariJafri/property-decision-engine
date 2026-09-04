"""Mortgage mathematics, Canadian conventions, integer cents.

**Semi-annual compounding is the thing to get right.** A Canadian fixed-rate
mortgage compounds twice a year, not monthly, so the monthly periodic rate is
``(1 + j/2)**(1/6) - 1`` and not ``j/12``. Using the American convention
overstates the payment by roughly 1% — about $30 a month on a $700,000 mortgage,
every month, on every file. It is the single most common error in a Canadian
mortgage calculator and it is silent.

**Insurance is priced on loan-to-value, then financed.** The premium is a
percentage of the loan, added to the principal and amortized, which means it also
accrues interest — a fact the trace makes visible because most buyers do not know
it.

Everything here is pure: value objects in, value objects and a trace out.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.core.money import Cents, apply_rate, cents
from app.engines.base import EngineResult, TraceBuilder
from app.engines.financial.contracts import (
    BuyerFinancials,
    MortgageResult,
    MortgageTerms,
    PropertyFinancials,
)
from app.engines.rules import RuleSet

MONTHS_PER_YEAR = 12


def monthly_periodic_rate(annual_nominal: Decimal, *, compounding_per_year: int = 2) -> Decimal:
    """The monthly rate equivalent to an annual nominal rate at Canadian compounding.

    ``(1 + j/m)**(m/12) - 1``. With ``m = 2`` this is the semi-annual convention;
    with ``m = 12`` it degenerates to ``j/12``, which is what a US calculator does
    and what we must not do here.
    """
    if annual_nominal < 0:
        raise ValueError("rate cannot be negative")
    if annual_nominal == 0:
        return Decimal(0)
    per_period = Decimal(1) + annual_nominal / Decimal(compounding_per_year)
    exponent = Decimal(compounding_per_year) / Decimal(MONTHS_PER_YEAR)
    # Decimal has no fractional power, and float's 15 significant digits are ample
    # here: the result is quantized to 12 places, far finer than a cent on any
    # realistic principal.
    return (Decimal(float(per_period) ** float(exponent)) - Decimal(1)).quantize(
        Decimal("0.000000000001")
    )


def payment_for(principal: Cents, periodic_rate: Decimal, periods: int) -> Cents:
    """Level payment that amortizes ``principal`` over ``periods``.

    ``P * i / (1 - (1 + i)**-n)``, and ``P / n`` when the rate is zero — a case
    that only shows up in tests and in vendor-take-back curiosities, but which
    would otherwise divide by zero.
    """
    if periods <= 0:
        raise ValueError("periods must be positive")
    if periodic_rate == 0:
        return cents(-(-principal // periods))  # ceiling, so the loan fully retires

    discount = Decimal(1) - Decimal(1) / (Decimal(1) + periodic_rate) ** periods
    payment = Decimal(principal) * periodic_rate / discount
    return cents(int(payment.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def first_year_split(
    principal: Cents, periodic_rate: Decimal, payment: Cents
) -> tuple[Cents, Cents]:
    """Interest and principal paid over the first twelve payments.

    Computed by walking the schedule rather than approximating, because the
    approximation is wrong by enough to be visible next to the real number, and
    this figure exists to be shown.
    """
    balance = Decimal(principal)
    interest_total = Decimal(0)
    for _ in range(MONTHS_PER_YEAR):
        interest = (balance * periodic_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        principal_part = min(Decimal(payment) - interest, balance)
        interest_total += interest
        balance -= principal_part
        if balance <= 0:
            break
    principal_total = Decimal(principal) - balance
    return cents(int(interest_total)), cents(int(principal_total))


def minimum_down_payment(price: Cents, rules: RuleSet, *, as_of: date) -> Cents:
    """The smallest down payment the insured-mortgage rules permit for this price.

    Tiered: 5% of the first $500,000, 10% of the portion to $1.5M, and 20% of the
    whole price above that, where insurance is unavailable at all.
    """
    tier_rule = rules.get("CA", "insured.down_payment_tiers", as_of=as_of)
    cap_rule = rules.get("CA", "insured.max_price_cents", as_of=as_of)
    insured_cap = cents(int(cap_rule.value["amount_cents"]))

    if price > insured_cap:
        return apply_rate(price, Decimal(str(tier_rule.value["uninsurable_min"])))

    tiers = [(int(t[0]), Decimal(str(t[1]))) for t in tier_rule.value["tiers"]]
    total = 0
    for index, (threshold, rate) in enumerate(tiers):
        if price <= threshold:
            break
        ceiling = tiers[index + 1][0] if index + 1 < len(tiers) else price
        portion = min(price, ceiling) - threshold
        total += apply_rate(cents(portion), rate)
    return cents(total)


def premium_rate_for(ltv: Decimal, rules: RuleSet, *, as_of: date) -> Decimal:
    """The insurance premium rate for a loan-to-value ratio, or zero at 80% or less."""
    bands = rules.get("CA", "insured.premium_bands", as_of=as_of).value["bands"]
    for ceiling, rate in bands:
        if ltv <= Decimal(str(ceiling)):
            return Decimal(str(rate))
    raise ValueError(f"loan-to-value {ltv} exceeds the insurable maximum")


def compute_mortgage(
    *,
    property_: PropertyFinancials,
    buyer: BuyerFinancials,
    terms: MortgageTerms,
    rules: RuleSet,
    as_of: date,
) -> EngineResult[MortgageResult]:
    """Principal, insurance, payment and the first year's split, with the working."""
    trace = TraceBuilder()
    price = property_.purchase_price_cents
    down = buyer.down_payment_cents

    base_principal = trace.step(
        "mortgage principal",
        "purchase_price - down_payment",
        {"purchase_price_cents": price, "down_payment_cents": down},
        cents(price - down),
        unit="cents",
    )
    if base_principal <= 0:
        raise ValueError("down payment covers the whole price; there is no mortgage")

    insured_cap = cents(
        int(rules.get("CA", "insured.max_price_cents", as_of=as_of).value["amount_cents"])
    )
    minimum = minimum_down_payment(price, rules, as_of=as_of)
    trace.step(
        "minimum down payment",
        "tiered: 5% to $500k, 10% to $1.5M, 20% above",
        {"purchase_price_cents": price},
        minimum,
        unit="cents",
        rule_keys=("CA/insured.down_payment_tiers", "CA/insured.max_price_cents"),
    )
    if down < minimum:
        raise ValueError(f"down payment {down} is below the {minimum} minimum for this price")

    ltv = (Decimal(base_principal) / Decimal(price)).quantize(Decimal("0.000001"))
    insured = price <= insured_cap and ltv > Decimal("0.80")
    trace.step(
        "loan to value",
        "principal / purchase_price",
        {"principal_cents": base_principal, "purchase_price_cents": price},
        str(ltv),
    )

    premium = cents(0)
    if insured:
        rate = premium_rate_for(ltv, rules, as_of=as_of)
        premium = trace.step(
            "mortgage insurance premium",
            "principal * premium_rate(ltv)",
            {"principal_cents": base_principal, "premium_rate": str(rate), "ltv": str(ltv)},
            apply_rate(base_principal, rate),
            unit="cents",
            rule_keys=("CA/insured.premium_bands",),
        )
        amortization_rule = rules.get("CA", "insured.max_amortization_years", as_of=as_of)
        long_amortization = terms.amortization_years > int(amortization_rule.value["standard"])
        if long_amortization:
            eligible = buyer.first_time_buyer or property_.is_new_build
            if not eligible:
                raise ValueError(
                    "a 30-year insured amortization requires a first-time buyer or a new build"
                )
            surcharge = rules.find("CA", "insured.amortization_surcharge", as_of=as_of)
            if surcharge is None:
                # The rule exists but is inactive because it is unverified. Say so;
                # a premium that is quietly 0.20% light is worse than a stated gap.
                trace.assume(
                    "insured.amortization_surcharge",
                    "excluded",
                    "A surcharge for 30-year insured amortizations is reported at 0.20% "
                    "but could not be confirmed against CMHC's published schedule, so it "
                    "is not charged here. Your lender's premium may be slightly higher.",
                    source_key="src_cmhc",
                )
    elif price > insured_cap:
        trace.assume(
            "insured",
            False,
            f"Purchase price exceeds the ${insured_cap // 100_000_00 / 10:.1f}M insurable "
            "maximum, so mortgage insurance is unavailable at any down payment.",
            source_key="src_cmhc",
        )

    principal = trace.step(
        "financed principal",
        "principal + insurance_premium",
        {"principal_cents": base_principal, "premium_cents": premium},
        cents(base_principal + premium),
        unit="cents",
    )

    periodic = monthly_periodic_rate(
        terms.contract_rate, compounding_per_year=terms.compounding_per_year
    )
    trace.step(
        "monthly periodic rate",
        "(1 + annual_rate / compounding_per_year) ** (compounding_per_year / 12) - 1",
        {
            "annual_rate": str(terms.contract_rate),
            "compounding_per_year": terms.compounding_per_year,
        },
        str(periodic),
    )

    periods = terms.amortization_years * MONTHS_PER_YEAR
    payment = trace.step(
        "monthly payment",
        "P * i / (1 - (1 + i) ** -n)",
        {"P_cents": principal, "i": str(periodic), "n": periods},
        payment_for(principal, periodic, periods),
        unit="cents",
    )

    interest_year_one, principal_year_one = first_year_split(principal, periodic, payment)
    trace.step(
        "first year interest",
        "sum of monthly interest over twelve payments",
        {"P_cents": principal, "i": str(periodic), "payment_cents": payment},
        interest_year_one,
        unit="cents",
    )

    result = MortgageResult(
        principal_cents=principal,
        insurance_premium_cents=premium,
        insured=insured,
        payment_cents=payment,
        effective_rate=terms.contract_rate,
        amortization_years=terms.amortization_years,
        first_year_interest_cents=interest_year_one,
        first_year_principal_cents=principal_year_one,
    )
    return trace.finish(result)
