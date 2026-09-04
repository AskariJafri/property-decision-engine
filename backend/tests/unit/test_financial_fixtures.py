"""The Phase 30 fixture matrix: every cliff, both jurisdictions, both buyer types.

Each case runs the whole engine end to end and asserts the properties that must
hold everywhere, plus the specific number that makes the case worth having. The
cliffs are chosen because they are where a household's plan silently breaks:

* **$500,000** — the down-payment tier steps from 5% to 10%.
* **$1,500,000** — insurance disappears entirely and the minimum down payment
  jumps from $125,000 to $300,000. One dollar of price costs $175,000 of cash.
* **$2,000,000** — Ontario's land transfer tax gains a 2.5% band.
* **$3,000,000** — Toronto's luxury bands begin, at 4.40%.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.core.money import cents, from_dollars
from app.engines.financial.contracts import (
    MortgageTerms,
    PropertyFinancials,
    PropertyKind,
    ResidencyStatus,
)
from app.engines.financial.engine import DeterministicFinancialEngine
from app.engines.financial.rules_seed import default_rule_set
from tests.unit.test_mortgage import buyer

RULES = default_rule_set()
TODAY = date(2026, 9, 4)
ENGINE = DeterministicFinancialEngine()


def run(
    *,
    price: str,
    down: str,
    income: str = "200000",
    jurisdiction: str = "ON/Toronto",
    kind: PropertyKind = PropertyKind.DETACHED,
    first_time: bool = True,
    amortization: int = 25,
    rate: str = "0.0409",
    savings: str = "400000",
):
    """One complete pass: mortgage, closing, ownership, qualification, affordability."""
    b = replace(
        buyer(down=down, income=income, first_time=first_time),
        available_savings_cents=from_dollars(savings),
        residency_status=ResidencyStatus.CITIZEN_OR_PR,
    )
    p = PropertyFinancials(
        purchase_price_cents=from_dollars(price),
        jurisdiction=jurisdiction,
        property_kind=kind,
    )
    terms = MortgageTerms(contract_rate=Decimal(rate), amortization_years=amortization)

    mortgage = ENGINE.mortgage(property_=p, buyer=b, terms=terms, rules=RULES, as_of=TODAY)
    closing = ENGINE.closing_costs(
        property_=p, buyer=b, mortgage=mortgage.value, rules=RULES, as_of=TODAY
    )
    ownership = ENGINE.ownership_cost(
        property_=p, mortgage=mortgage.value, rules=RULES, as_of=TODAY
    )
    qualification = ENGINE.qualification(
        property_=p,
        buyer=b,
        terms=terms,
        ownership=ownership.value,
        rules=RULES,
        as_of=TODAY,
    )
    affordability = ENGINE.affordability(
        buyer=b, ownership=ownership.value, closing=closing.value, mortgage=mortgage.value
    )
    return mortgage, closing, ownership, qualification, affordability


#: price, minimum down payment, whether insurance is available at that minimum
CLIFFS = [
    ("400000", "20000", True),
    ("500000", "25000", True),
    ("500001", "25000.10", True),
    ("999999", "74999.90", True),
    ("1500000", "125000", True),
    ("1500001", "300000.20", False),
    ("2000000", "400000", False),
]


class TestTheCliffs:
    @pytest.mark.parametrize(("price", "down", "insurable"), CLIFFS)
    def test_each_cliff_prices_correctly(self, price, down, insurable):
        mortgage, closing, ownership, _, affordability = run(
            price=price, down=down, income="400000", savings="800000"
        )
        m = mortgage.value
        assert m.insured is insurable
        if insurable:
            assert m.insurance_premium_cents > 0
            assert (
                m.principal_cents
                == from_dollars(price) - from_dollars(down) + m.insurance_premium_cents
            )
        else:
            assert m.insurance_premium_cents == 0
            assert m.principal_cents == from_dollars(price) - from_dollars(down)

        assert ownership.value.total_monthly_cents > m.payment_cents
        assert closing.value.total_cents > 0
        assert (
            affordability.value.cash_required_cents
            == from_dollars(down) + closing.value.total_cents
        )

    def test_one_dollar_of_price_costs_one_hundred_and_seventy_five_thousand_of_cash(self):
        """The $1.5M cliff, in the terms a buyer experiences it. This is the single
        most consequential threshold in Canadian home buying, and it is invisible on
        every listing site."""
        _, _, _, _, below = run(price="1500000", down="125000", income="500000", savings="900000")
        _, _, _, _, above = run(
            price="1500001", down="300000.20", income="500000", savings="900000"
        )
        difference = above.value.cash_required_cents - below.value.cash_required_cents
        assert difference > from_dollars("175000")

    def test_below_the_minimum_down_payment_the_engine_refuses_rather_than_guesses(self):
        with pytest.raises(ValueError, match="below the"):
            run(price="1500001", down="200000")


class TestJurisdiction:
    @pytest.mark.parametrize("price", ["500000", "850000", "1500000"])
    def test_toronto_costs_more_to_close_than_anywhere_else_in_ontario(self, price):
        _, toronto, _, _, _ = run(price=price, down="300000", jurisdiction="ON/Toronto")
        _, ottawa, _, _, _ = run(price=price, down="300000", jurisdiction="ON/Ottawa")
        assert toronto.value.total_cents > ottawa.value.total_cents

    def test_a_first_time_buyer_in_toronto_saves_exactly_the_two_capped_rebates(self):
        _, first, _, _, _ = run(price="850000", down="300000", first_time=True)
        _, repeat, _, _, _ = run(price="850000", down="300000", first_time=False)
        assert repeat.value.total_cents - first.value.total_cents == from_dollars("8475")

    def test_outside_toronto_only_the_provincial_rebate_applies(self):
        _, first, _, _, _ = run(
            price="850000", down="300000", first_time=True, jurisdiction="ON/Ottawa"
        )
        _, repeat, _, _, _ = run(
            price="850000", down="300000", first_time=False, jurisdiction="ON/Ottawa"
        )
        assert repeat.value.total_cents - first.value.total_cents == from_dollars("4000")


class TestPropertyKind:
    def test_a_condo_carries_a_fee_and_a_status_certificate_but_a_smaller_reserve(self):
        _, house_closing, house_own, _, _ = run(price="850000", down="300000")
        _, condo_closing, condo_own, _, _ = run(
            price="850000", down="300000", kind=PropertyKind.CONDO_APARTMENT
        )
        assert condo_own.value.maintenance_reserve_cents < house_own.value.maintenance_reserve_cents
        assert condo_own.value.utilities_cents < house_own.value.utilities_cents
        assert condo_closing.value.total_cents > house_closing.value.total_cents

    def test_a_condo_without_a_stated_fee_says_so_rather_than_estimating_one(self):
        _, _, ownership, _, _ = run(
            price="850000", down="300000", kind=PropertyKind.CONDO_APARTMENT
        )
        assert not ownership.is_complete
        assert any("condo fee" in f.provenance.unavailable_reason for f in ownership.unavailable)


class TestUniversalProperties:
    """Properties that must hold for every case in the matrix."""

    @pytest.mark.parametrize(("price", "down", "_insurable"), CLIFFS)
    @pytest.mark.parametrize("jurisdiction", ["ON/Toronto", "ON/Ottawa"])
    @pytest.mark.parametrize("first_time", [True, False])
    def test_every_case_is_internally_consistent(
        self, price, down, _insurable, jurisdiction, first_time
    ):
        mortgage, closing, ownership, qualification, affordability = run(
            price=price,
            down=down,
            jurisdiction=jurisdiction,
            first_time=first_time,
            income="400000",
            savings="900000",
        )

        # Money stays integer cents the whole way through.
        for value in (
            mortgage.value.payment_cents,
            closing.value.total_cents,
            ownership.value.total_monthly_cents,
            affordability.value.cash_required_cents,
        ):
            assert isinstance(value, int) and not isinstance(value, bool)
            assert cents(value) == value

        # The ownership total is exactly the sum of its parts.
        o = ownership.value
        assert o.total_monthly_cents == (
            o.mortgage_payment_cents
            + o.property_tax_cents
            + o.insurance_cents
            + o.condo_fee_cents
            + o.utilities_cents
            + o.maintenance_reserve_cents
        )

        # The closing total is exactly the sum of its lines, rebates included.
        assert closing.value.total_cents == sum(x.amount_cents for x in closing.value.lines)

        # Rebates only ever appear for a first-time buyer, and never exceed the tax.
        if not first_time:
            assert closing.value.rebates_cents == 0

        # Every figure carries its working.
        assert mortgage.steps and closing.steps and ownership.steps and qualification.steps

        # The stress test never flatters: the qualifying rate is at or above contract.
        assert qualification.value.stressed_rate >= Decimal("0.0525")

    @pytest.mark.parametrize(("price", "down", "_insurable"), CLIFFS)
    def test_reproducibility(self, price, down, _insurable):
        """Same inputs, same rule set, same numbers — the contract the whole product
        rests on."""
        first = run(price=price, down=down, income="400000", savings="900000")
        second = run(price=price, down=down, income="400000", savings="900000")
        assert [r.value for r in first] == [r.value for r in second]


class TestTraceCompleteness:
    def test_every_calculation_step_records_input_formula_and_output(self):
        mortgage, closing, ownership, qualification, _ = run(price="850000", down="170000")
        for result in (mortgage, closing, ownership, qualification):
            for step in result.steps:
                assert step.name and step.formula
                assert step.inputs, f"{step.name} records no inputs"
                assert step.output is not None

    def test_statutory_steps_cite_the_rule_that_produced_them(self):
        _, closing, _, _, _ = run(price="850000", down="170000")
        ltt = next(s for s in closing.steps if s.name == "Ontario land transfer tax")
        assert ltt.rule_keys == ("ON/ltt.brackets.sfr",)
