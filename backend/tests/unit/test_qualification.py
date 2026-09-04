"""The qualification estimate, and its distance from affordability."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.core.money import from_dollars
from app.engines.financial.contracts import MortgageTerms, PropertyKind
from app.engines.financial.engine import DeterministicFinancialEngine
from app.engines.financial.qualification import stressed_rate
from app.engines.financial.rules_seed import default_rule_set
from tests.unit.test_mortgage import buyer, prop

RULES = default_rule_set()
TODAY = date(2026, 9, 4)
ENGINE = DeterministicFinancialEngine()
TERMS = MortgageTerms(contract_rate=Decimal("0.0409"), amortization_years=25)


def assess(
    *,
    price="850000",
    down="170000",
    income="150000",
    debts="0",
    kind=PropertyKind.DETACHED,
    terms=TERMS,
    condo_fee=None,
    tax=None,
):
    b = replace(
        buyer(down=down, income=income),
        monthly_debt_payments_cents=from_dollars(debts),
    )
    p = prop(price=price, kind=kind)
    if condo_fee or tax:
        p = replace(
            p,
            monthly_condo_fee_cents=from_dollars(condo_fee) if condo_fee else None,
            annual_property_tax_cents=from_dollars(tax) if tax else None,
        )
    mortgage = ENGINE.mortgage(property_=p, buyer=b, terms=terms, rules=RULES, as_of=TODAY).value
    ownership = ENGINE.ownership_cost(
        property_=p, mortgage=mortgage, rules=RULES, as_of=TODAY
    ).value
    return ENGINE.qualification(
        property_=p, buyer=b, terms=terms, ownership=ownership, rules=RULES, as_of=TODAY
    )


class TestMinimumQualifyingRate:
    @pytest.mark.parametrize(
        ("contract", "expected"),
        [
            ("0.0300", "0.0525"),  # the floor binds
            ("0.0325", "0.0525"),  # exactly at the crossover
            ("0.0409", "0.0609"),  # contract + 2% binds
            ("0.0600", "0.0800"),
        ],
    )
    def test_greater_of_floor_and_contract_plus_buffer(self, contract, expected):
        assert stressed_rate(Decimal(contract), RULES, as_of=TODAY) == Decimal(expected)

    def test_the_stress_test_only_stresses_the_payment(self):
        """Taxes, heat and condo fees are not re-rated. Stressing the whole ownership
        cost would be a harsher test than any lender actually applies."""
        result = assess()
        payment_step = next(s for s in result.steps if s.name == "stressed payment")
        housing_step = next(s for s in result.steps if s.name == "qualifying housing costs")
        assert housing_step.inputs["stressed_payment_cents"] == payment_step.output
        assert housing_step.inputs["property_tax_cents"] > 0


class TestRatios:
    def test_a_comfortable_file_qualifies(self):
        result = assess(price="700000", down="140000", income="180000")
        assert result.value.may_qualify is True
        assert result.value.gds < result.value.gds_limit
        assert not result.value.blocking_reasons

    def test_debts_push_a_file_over_tds_without_touching_gds(self):
        clean = assess(price="850000", down="170000", income="150000", debts="0")
        laden = assess(price="850000", down="170000", income="150000", debts="1800")
        assert clean.value.gds == laden.value.gds
        assert laden.value.tds > clean.value.tds

    def test_exceeding_a_limit_is_reported_in_words(self):
        result = assess(price="1400000", down="280000", income="120000")
        assert result.value.may_qualify is False
        assert any("debt service" in reason for reason in result.value.blocking_reasons)

    def test_a_condo_counts_half_its_fee_and_a_lower_heat_floor(self):
        with_fee = assess(kind=PropertyKind.CONDO_APARTMENT, condo_fee="800", tax="4000")
        no_fee = assess(kind=PropertyKind.CONDO_APARTMENT, condo_fee="0", tax="4000")
        step = next(s for s in with_fee.steps if s.name == "qualifying housing costs")
        assert step.inputs["condo_component_cents"] == from_dollars("400")
        assert step.inputs["heat_cents"] == from_dollars("100")
        assert with_fee.value.gds > no_fee.value.gds


class TestMaximumSupportedPrice:
    def test_it_is_a_price_the_file_actually_clears(self):
        result = assess(price="700000", down="140000", income="180000")
        maximum = result.value.max_purchase_price_cents
        assert maximum is not None and maximum > from_dollars("500000")

        at_max = assess(price=str(maximum // 100), down="140000", income="180000")
        assert at_max.value.gds <= at_max.value.gds_limit + Decimal("0.005")

    def test_more_income_supports_more_price(self):
        modest = assess(income="120000").value.max_purchase_price_cents
        comfortable = assess(income="200000").value.max_purchase_price_cents
        assert modest is not None and comfortable is not None
        assert comfortable > modest

    def test_debt_reduces_it(self):
        clean = assess(debts="0").value.max_purchase_price_cents
        laden = assess(debts="1500").value.max_purchase_price_cents
        assert clean is not None and laden is not None
        assert laden < clean

    def test_it_is_deterministic(self):
        # Bisection with a fixed iteration count, so no run-to-run drift.
        assert assess().value.max_purchase_price_cents == assess().value.max_purchase_price_cents


class TestTheDisclaimerTravelsWithTheNumber:
    def test_every_estimate_carries_its_own_caveat(self):
        """COMPLIANCE.md §1: the caveat is part of the payload, not a UI footer that
        a restyle can lose."""
        estimate = assess().value
        assert "lender" in estimate.disclaimer.lower()
        assert "estimate" in estimate.disclaimer.lower()


class TestAffordabilityIsADifferentQuestion:
    def test_a_file_can_qualify_and_still_be_a_strain(self):
        """The gap the product exists to show. A lender looks at stressed ratios
        against published limits; a household looks at what is left over."""
        b = replace(
            buyer(down="170000", income="190000"),
            available_savings_cents=from_dollars("175000"),
            emergency_fund_cents=from_dollars("0"),
            desired_max_monthly_cents=from_dollars("3500"),
        )
        p = prop(price="850000")
        mortgage = ENGINE.mortgage(
            property_=p, buyer=b, terms=TERMS, rules=RULES, as_of=TODAY
        ).value
        ownership = ENGINE.ownership_cost(
            property_=p, mortgage=mortgage, rules=RULES, as_of=TODAY
        ).value
        closing = ENGINE.closing_costs(
            property_=p, buyer=b, mortgage=mortgage, rules=RULES, as_of=TODAY
        ).value
        qualification = ENGINE.qualification(
            property_=p, buyer=b, terms=TERMS, ownership=ownership, rules=RULES, as_of=TODAY
        ).value
        affordability = ENGINE.affordability(
            buyer=b, ownership=ownership, closing=closing, mortgage=mortgage
        ).value

        assert qualification.may_qualify is True
        # ...and yet: over the stated budget, and no reserve left after closing.
        assert affordability.budget_ratio is not None and affordability.budget_ratio > 1
        assert affordability.reserve_months < Decimal("1")
        assert affordability.cash_shortfall_cents > 0
