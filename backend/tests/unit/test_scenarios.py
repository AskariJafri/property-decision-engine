"""Projections, the missing-information checklist, personal fit and comparison."""

from decimal import Decimal
from typing import Any, ClassVar

import pytest

from app.engines.financial.mortgage import monthly_periodic_rate, payment_for, schedule_by_year
from app.engines.risk.missing_info import MissingInfoInput, missing_information
from app.engines.scenarios.comparison import ComparisonInput, compare
from app.engines.scenarios.personal import PersonalInput, personal_fit
from app.engines.scenarios.projection import ProjectionAssumptions, ProjectionInput, project

FLAT = ProjectionAssumptions(
    appreciation_rates=(Decimal("0"), Decimal("0.03")),
    selling_cost_rate=Decimal("0.05"),
    opportunity_return_rate=Decimal("0"),
    property_tax_growth=Decimal("0"),
    condo_fee_growth=Decimal("0"),
    insurance_growth=Decimal("0"),
    maintenance_growth=Decimal("0"),
    utilities_growth=Decimal("0"),
)


def facts(**overrides):
    base: ClassVar[dict[str, Any]] = {
        "purchase_price_cents": 50_000_000,
        "down_payment_cents": 40_000_000,
        "closing_costs_cents": 1_000_000,
        "financed_principal_cents": 10_000_000,
        "contract_rate": Decimal("0"),
        "amortization_years": 10,
        "monthly_payment_cents": 83_334,
        "monthly_property_tax_cents": 10_000,
        "monthly_insurance_cents": 0,
        "monthly_condo_fee_cents": 0,
        "monthly_utilities_cents": 0,
        "monthly_maintenance_cents": 0,
    }
    return ProjectionInput(**{**base, **overrides})


class TestProjectionByHand:
    """A zero-rate loan makes every figure checkable with a pencil."""

    def test_five_years_of_a_zero_rate_loan(self):
        five = project(facts(), FLAT).horizons[0]
        assert five.years == 5
        assert five.interest_paid_cents == 0
        # 60 payments of $833.34 against $100,000.
        assert five.principal_repaid_cents == 60 * 83_334
        assert five.mortgage_balance_cents == 10_000_000 - 60 * 83_334
        assert five.property_tax_cents == 10_000 * 12 * 5

    def test_the_loan_is_retired_at_ten_years_and_stays_retired(self):
        ten = project(facts(), FLAT).horizons[1]
        assert ten.mortgage_balance_cents == 0
        assert ten.principal_repaid_cents == 10_000_000

    def test_no_appreciation_nets_out_to_costs_that_do_not_come_back(self):
        ten = project(facts(), FLAT).horizons[1]
        flat = ten.outcomes[0]
        assert flat.rate == 0
        assert flat.home_value_cents == 50_000_000
        assert flat.selling_costs_cents == 2_500_000
        # Paid out: down + closing + loan + tax. Returned: value - selling - balance.
        outlay = 40_000_000 + 1_000_000 + 10_000_000 + 10_000 * 120
        assert ten.total_outlay_cents == outlay
        assert flat.net_cost_cents == outlay - (50_000_000 - 2_500_000)

    def test_growth_compounds_annually(self):
        grown = project(facts(), FLAT).horizons[0].outcomes[1]
        assert grown.home_value_cents == round(50_000_000 * 1.03**5)


class TestProjectionAgainstTheClosedForm:
    def test_the_walked_balance_matches_the_formula(self):
        principal, rate, years = 60_000_000, Decimal("0.0489"), 25
        i = monthly_periodic_rate(rate)
        payment = payment_for(principal, i, years * 12)
        walked = schedule_by_year(principal, i, payment, 5)[-1][2]
        n = 60
        growth = (1 + float(i)) ** n
        closed = principal * growth - payment * (growth - 1) / float(i)
        assert abs(walked - closed) < 100  # within a dollar after 60 rounded months

    def test_a_higher_rate_raises_the_payment(self):
        result = project(
            facts(
                contract_rate=Decimal("0.05"),
                amortization_years=25,
                financed_principal_cents=60_000_000,
                monthly_payment_cents=payment_for(
                    60_000_000, monthly_periodic_rate(Decimal("0.05")), 300
                ),
            ),
            FLAT,
        )
        payments = [r.monthly_payment_cents for r in result.rate_sensitivity]
        assert payments == sorted(payments)
        assert [float(r.rate) for r in result.rate_sensitivity] == [0.04, 0.05, 0.06, 0.07]


def checklist(**overrides):
    base: ClassVar[dict[str, Any]] = {
        "property_kind": "detached",
        "annual_property_tax_supplied": True,
        "property_tax_estimated": False,
        "monthly_condo_fee_supplied": False,
        "year_built": 2015,
        "as_of_year": 2026,
        "square_feet": 1400,
        "bedrooms": 3,
        "address_supplied": True,
        "comparables_included": 3,
    }
    return {i.key: i for i in missing_information(MissingInfoInput(**{**base, **overrides}))}


class TestMissingInformation:
    def test_every_item_says_why_and_what_to_ask(self):
        for item in checklist(property_kind="condo_apartment", year_built=None).values():
            assert item.why_it_matters and item.what_to_ask_for

    def test_a_condo_without_a_fee_asks_for_it_and_the_status_certificate(self):
        items = checklist(property_kind="condo_apartment")
        assert {"condo_fee", "status_certificate", "reserve_fund"} <= set(items)
        assert "roof_age" not in items

    def test_a_house_asks_about_the_roof_and_mechanicals(self):
        items = checklist()
        assert {"roof_age", "hvac_age"} <= set(items)
        assert "status_certificate" not in items

    def test_an_old_house_raises_wiring_and_the_roof_is_not_low_priority(self):
        items = checklist(year_built=1950)
        assert "electrical_plumbing" in items
        assert items["roof_age"].severity == "medium"

    def test_tax_and_comparables_gaps(self):
        items = checklist(
            annual_property_tax_supplied=False, property_tax_estimated=True, comparables_included=1
        )
        assert items["property_tax"].title == "Property taxes not confirmed"
        assert "comparables" in items

    def test_high_priority_items_come_first(self):
        ordered = missing_information(
            MissingInfoInput(
                property_kind="condo_apartment",
                annual_property_tax_supplied=False,
                property_tax_estimated=False,
                monthly_condo_fee_supplied=False,
                year_built=None,
                as_of_year=2026,
                square_feet=None,
                bedrooms=None,
                address_supplied=False,
                comparables_included=0,
            )
        )
        severities = [i.severity for i in ordered]
        assert severities == sorted(severities, key={"high": 0, "medium": 1, "low": 2}.get)


class TestPersonalFit:
    base: ClassVar[dict[str, Any]] = {
        "gross_annual_income_cents": 12_000_000,
        "monthly_net_income_cents": None,
        "monthly_debt_payments_cents": 50_000,
        "other_monthly_expenses_cents": None,
        "monthly_housing_cost_cents": 400_000,
        "cash_required_cents": 9_000_000,
        "available_savings_cents": 10_000_000,
        "emergency_fund_cents": 1_350_000,
    }

    def lines(self, **overrides):
        fit = personal_fit(PersonalInput(**{**self.base, **overrides}))
        return fit, {line.key: line for line in fit.lines}

    def test_without_take_home_pay_the_remainder_is_labelled_before_tax(self):
        fit, lines = self.lines()
        assert lines["remaining_income"].amount_cents == 1_000_000 - 400_000 - 50_000
        assert "before tax" in lines["remaining_income"].label
        assert lines["remaining_income"].basis == "estimated"
        assert fit.housing_share_of_gross == Decimal("0.4")
        assert fit.emergency_months == Decimal("3.0")

    def test_take_home_pay_and_other_expenses_are_used_when_given(self):
        _, lines = self.lines(
            monthly_net_income_cents=700_000, other_monthly_expenses_cents=100_000
        )
        assert lines["remaining_income"].amount_cents == 700_000 - 400_000 - 50_000 - 100_000
        assert lines["remaining_income"].basis == "user_provided"

    def test_remaining_savings_can_be_a_shortfall(self):
        _, lines = self.lines(cash_required_cents=12_000_000)
        assert lines["remaining_savings"].amount_cents == -2_000_000


def item(label, **overrides):
    base: ClassVar[dict[str, Any]] = {
        "label": label,
        "purchase_price_cents": 80_000_000,
        "down_payment_cents": 16_000_000,
        "mortgage_principal_cents": 64_000_000,
        "monthly_payment_cents": 350_000,
        "monthly_property_tax_cents": 50_000,
        "monthly_condo_fee_cents": 0,
        "monthly_insurance_cents": 15_000,
        "monthly_maintenance_cents": 60_000,
        "monthly_carrying_cost_cents": 500_000,
        "closing_costs_cents": 2_000_000,
        "cash_required_cents": 18_000_000,
        "five_year_outlay_cents": 50_000_000,
        "ten_year_outlay_cents": 80_000_000,
        "ten_year_equity_no_growth_cents": 20_000_000,
        "ten_year_equity_mid_growth_cents": 30_000_000,
        "risk_count": 0,
        "missing_count": 4,
        "high_priority_missing": 0,
    }
    return ComparisonInput(**{**base, **overrides})


class TestComparison:
    def test_a_monthly_versus_upfront_trade_off_is_stated_both_ways(self):
        result = compare(
            [
                item("A"),
                item("B", monthly_carrying_cost_cents=450_000, cash_required_cents=20_000_000),
            ]
        )
        assert any(
            "B costs $500 a month less" in t and "$20,000 more cash" in t for t in result.trade_offs
        )

    def test_identical_properties_have_no_differences(self):
        assert compare([item("A"), item("B")]).differences == ()

    def test_it_never_names_a_winner(self):
        result = compare([item("A"), item("B", purchase_price_cents=70_000_000, risk_count=2)])
        text = " ".join(result.trade_offs + tuple(d.sentence for d in result.differences))
        for word in ("best", "winner", "recommend", "should buy"):
            assert word not in text.lower()

    def test_between_two_and_five(self):
        with pytest.raises(ValueError):
            compare([item("A")])
        with pytest.raises(ValueError):
            compare([item(str(i)) for i in range(6)])
