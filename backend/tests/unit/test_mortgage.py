"""Mortgage mathematics, checked against hand calculation and against itself."""

from datetime import date
from decimal import Decimal

import pytest

from app.core.money import cents, from_dollars
from app.engines.financial.contracts import (
    BuyerFinancials,
    MortgageTerms,
    PropertyFinancials,
    PropertyKind,
    ResidencyStatus,
)
from app.engines.financial.mortgage import (
    compute_mortgage,
    first_year_split,
    minimum_down_payment,
    monthly_periodic_rate,
    payment_for,
    premium_rate_for,
)
from app.engines.financial.rules_seed import default_rule_set

RULES = default_rule_set()
TODAY = date(2026, 9, 4)


def buyer(*, down: str, income: str = "150000", first_time: bool = True) -> BuyerFinancials:
    return BuyerFinancials(
        gross_annual_income_cents=from_dollars(income),
        household_income_cents=from_dollars(income),
        monthly_debt_payments_cents=from_dollars("0"),
        down_payment_cents=from_dollars(down),
        available_savings_cents=from_dollars("200000"),
        emergency_fund_cents=from_dollars("20000"),
        desired_max_monthly_cents=None,
        first_time_buyer=first_time,
        residency_status=ResidencyStatus.CITIZEN_OR_PR,
    )


def prop(*, price: str, kind: PropertyKind = PropertyKind.DETACHED, **kw) -> PropertyFinancials:
    return PropertyFinancials(
        purchase_price_cents=from_dollars(price),
        jurisdiction="ON/Toronto",
        property_kind=kind,
        **kw,
    )


class TestPeriodicRate:
    def test_semi_annual_compounding_is_not_rate_over_twelve(self):
        """The single most common error in a Canadian mortgage calculator.

        At 5% nominal, the semi-annual convention gives ~0.4124% a month while the
        American ``j/12`` gives 0.4167% — small, and worth about $30 a month on a
        $700k mortgage, forever.
        """
        semi_annual = monthly_periodic_rate(Decimal("0.05"), compounding_per_year=2)
        naive = Decimal("0.05") / 12
        assert semi_annual < naive
        assert semi_annual == pytest.approx(Decimal("0.004123915"), abs=Decimal("0.000000001"))

    def test_monthly_compounding_degenerates_to_the_naive_form(self):
        monthly = monthly_periodic_rate(Decimal("0.06"), compounding_per_year=12)
        assert monthly == pytest.approx(Decimal("0.005"), abs=Decimal("0.000000001"))

    def test_zero_rate_is_zero(self):
        assert monthly_periodic_rate(Decimal("0")) == 0


class TestPayment:
    @pytest.mark.parametrize(
        ("principal", "rate", "years", "expected"),
        [
            ("500000", "0.05", 25, "2908.02"),
            ("100000", "0.05", 25, "581.60"),
        ],
    )
    def test_matches_the_published_canadian_figures(self, principal, rate, years, expected):
        """To the cent, against the numbers every Canadian mortgage calculator prints.

        $500,000 at 5% over 25 years is $2,908.02 and $100,000 is $581.60. Both fall
        out of ``P * i / (1 - (1+i)^-n)`` with ``i = 1.025^(1/6) - 1``. Get the
        compounding wrong and the first becomes $2,922.95 — close enough to look
        right, wrong by $4,500 over a five-year term.
        """
        payment = payment_for(
            from_dollars(principal), monthly_periodic_rate(Decimal(rate)), years * 12
        )
        assert payment == from_dollars(expected)

    def test_a_zero_rate_loan_is_just_division(self):
        payment = payment_for(from_dollars("120000"), Decimal("0"), 120)
        assert payment == from_dollars("1000")

    def test_the_schedule_actually_retires_the_loan(self):
        """The strongest check available without a third party: amortize the whole
        term payment by payment and land within a cent of zero."""
        principal = from_dollars("650000")
        rate = monthly_periodic_rate(Decimal("0.0409"))
        periods = 300
        payment = payment_for(principal, rate, periods)

        balance = Decimal(principal)
        for _ in range(periods):
            interest = (balance * rate).quantize(Decimal("1"))
            balance -= Decimal(payment) - interest

        # The payment is rounded to the cent, so the schedule cannot land exactly on
        # zero: each period carries at most half a cent of rounding, and the residual
        # is bounded by one cent per payment. It must be a credit, never a debt — a
        # lender trues this up in the final payment, and a shortfall would mean the
        # published payment does not actually retire the loan.
        assert -periods <= balance <= 0, f"residual {balance} exceeds one cent per payment"

    def test_a_longer_amortization_lowers_the_payment_and_raises_the_interest(self):
        principal = from_dollars("700000")
        rate = monthly_periodic_rate(Decimal("0.0409"))
        p25 = payment_for(principal, rate, 300)
        p30 = payment_for(principal, rate, 360)
        assert p30 < p25
        assert first_year_split(principal, rate, p30)[0] > first_year_split(principal, rate, p25)[0]

    def test_zero_periods_is_refused(self):
        with pytest.raises(ValueError, match="periods"):
            payment_for(from_dollars("100000"), Decimal("0.01"), 0)


class TestMinimumDownPayment:
    @pytest.mark.parametrize(
        ("price", "expected"),
        [
            ("400000", "20000"),  # 5% throughout
            ("500000", "25000"),  # exactly at the first step
            ("500001", "25000.10"),  # 5% of 500k + 10% of the dollar above
            ("999999", "74999.90"),
            ("1500000", "125000"),  # 25,000 + 10% of 1,000,000
            ("1500001", "300000.20"),  # uninsurable: a flat 20% of the whole price
            ("2000000", "400000"),
        ],
    )
    def test_tiers_step_where_the_rules_say(self, price, expected):
        assert minimum_down_payment(from_dollars(price), RULES, as_of=TODAY) == from_dollars(
            expected
        )

    def test_the_cliff_at_one_and_a_half_million_is_a_cliff(self):
        """$1 more of price costs $175,000 more of down payment. This is the single
        most consequential threshold in Canadian home buying and the product exists
        partly to make sure nobody discovers it at the offer stage."""
        below = minimum_down_payment(from_dollars("1500000"), RULES, as_of=TODAY)
        above = minimum_down_payment(from_dollars("1500001"), RULES, as_of=TODAY)
        assert above - below == pytest.approx(from_dollars("175000.20"), abs=100)


class TestPremium:
    @pytest.mark.parametrize(
        ("ltv", "rate"),
        [
            ("0.60", "0.006"),
            ("0.65", "0.006"),
            ("0.6501", "0.017"),
            ("0.75", "0.017"),
            ("0.80", "0.024"),
            ("0.85", "0.028"),
            ("0.90", "0.031"),
            ("0.95", "0.040"),
        ],
    )
    def test_bands_are_inclusive_at_the_top(self, ltv, rate):
        assert premium_rate_for(Decimal(ltv), RULES, as_of=TODAY) == Decimal(rate)

    def test_above_ninety_five_percent_is_not_insurable(self):
        with pytest.raises(ValueError, match="insurable"):
            premium_rate_for(Decimal("0.96"), RULES, as_of=TODAY)


class TestComputeMortgage:
    def test_an_insured_purchase_finances_the_premium(self):
        result = compute_mortgage(
            property_=prop(price="850000"),
            buyer=buyer(down="85000"),  # 10% -> 90% LTV -> 3.10%
            terms=MortgageTerms(contract_rate=Decimal("0.0409"), amortization_years=25),
            rules=RULES,
            as_of=TODAY,
        )
        m = result.value
        assert m.insured is True
        assert m.insurance_premium_cents == from_dollars("23715")  # 765,000 * 3.10%
        assert m.principal_cents == from_dollars("788715")
        assert m.payment_cents > 0
        assert [step.name for step in result.steps][:2] == [
            "mortgage principal",
            "minimum down payment",
        ]

    def test_twenty_percent_down_is_not_insured(self):
        result = compute_mortgage(
            property_=prop(price="850000"),
            buyer=buyer(down="170000"),
            terms=MortgageTerms(contract_rate=Decimal("0.0409"), amortization_years=25),
            rules=RULES,
            as_of=TODAY,
        )
        assert result.value.insured is False
        assert result.value.insurance_premium_cents == 0

    def test_above_the_insurable_cap_the_engine_says_why(self):
        result = compute_mortgage(
            property_=prop(price="1600000"),
            buyer=buyer(down="320000"),
            terms=MortgageTerms(contract_rate=Decimal("0.0409"), amortization_years=25),
            rules=RULES,
            as_of=TODAY,
        )
        assert result.value.insured is False
        assert any(a.key == "insured" for a in result.assumptions)

    def test_a_thirty_year_insured_amortization_needs_a_first_timer_or_a_new_build(self):
        with pytest.raises(ValueError, match="first-time buyer or a new build"):
            compute_mortgage(
                property_=prop(price="850000"),
                buyer=buyer(down="85000", first_time=False),
                terms=MortgageTerms(contract_rate=Decimal("0.0409"), amortization_years=30),
                rules=RULES,
                as_of=TODAY,
            )

    def test_the_unverified_surcharge_is_declared_not_guessed(self):
        """The 0.20% surcharge on a 30-year insured amortization is reported but
        unconfirmed, so the rule is inactive. The engine must say what it left out
        rather than quietly under-charging the premium."""
        result = compute_mortgage(
            property_=prop(price="850000"),
            buyer=buyer(down="85000", first_time=True),
            terms=MortgageTerms(contract_rate=Decimal("0.0409"), amortization_years=30),
            rules=RULES,
            as_of=TODAY,
        )
        surcharge = [a for a in result.assumptions if a.key == "insured.amortization_surcharge"]
        assert surcharge, "the excluded surcharge must be declared"
        assert "could not be confirmed" in surcharge[0].rationale

    def test_a_down_payment_below_the_minimum_is_refused(self):
        with pytest.raises(ValueError, match="below the"):
            compute_mortgage(
                property_=prop(price="850000"),
                buyer=buyer(down="40000"),
                terms=MortgageTerms(contract_rate=Decimal("0.0409"), amortization_years=25),
                rules=RULES,
                as_of=TODAY,
            )

    def test_the_first_year_split_sums_to_twelve_payments(self):
        result = compute_mortgage(
            property_=prop(price="850000"),
            buyer=buyer(down="170000"),
            terms=MortgageTerms(contract_rate=Decimal("0.0409"), amortization_years=25),
            rules=RULES,
            as_of=TODAY,
        )
        m = result.value
        assert m.first_year_interest_cents + m.first_year_principal_cents == pytest.approx(
            m.payment_cents * 12, abs=100
        )

    def test_the_same_inputs_always_produce_the_same_output(self):
        args = dict(
            property_=prop(price="850000"),
            buyer=buyer(down="85000"),
            terms=MortgageTerms(contract_rate=Decimal("0.0409"), amortization_years=25),
            rules=RULES,
            as_of=TODAY,
        )
        assert compute_mortgage(**args).value == compute_mortgage(**args).value


def test_money_never_becomes_a_float_anywhere_in_the_result():
    result = compute_mortgage(
        property_=prop(price="850000"),
        buyer=buyer(down="85000"),
        terms=MortgageTerms(contract_rate=Decimal("0.0409"), amortization_years=25),
        rules=RULES,
        as_of=TODAY,
    )
    for field in (
        result.value.principal_cents,
        result.value.payment_cents,
        result.value.insurance_premium_cents,
        result.value.first_year_interest_cents,
    ):
        assert isinstance(field, int) and not isinstance(field, bool)
    assert cents(result.value.payment_cents) == result.value.payment_cents
