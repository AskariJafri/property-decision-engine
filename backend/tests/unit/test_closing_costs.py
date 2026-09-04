"""Land transfer taxes, rebates, and the April 2026 luxury bands."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.core.money import from_dollars
from app.engines.financial.closing_costs import compute_closing_costs, marginal_tax
from app.engines.financial.contracts import (
    MortgageResult,
    PropertyFinancials,
    PropertyKind,
    ResidencyStatus,
)
from app.engines.financial.rules_seed import default_rule_set
from app.engines.rules import RuleSet
from tests.unit.test_mortgage import buyer

RULES: RuleSet = default_rule_set()
TODAY = date(2026, 9, 4)
BEFORE_LUXURY = date(2026, 3, 31)

NO_MORTGAGE = MortgageResult(
    principal_cents=from_dollars("0"),
    insurance_premium_cents=from_dollars("0"),
    insured=False,
    payment_cents=from_dollars("0"),
    effective_rate=Decimal("0.04"),
    amortization_years=25,
    first_year_interest_cents=from_dollars("0"),
    first_year_principal_cents=from_dollars("0"),
)


def prop(price: str, *, jurisdiction: str = "ON/Toronto", kind=PropertyKind.DETACHED):
    return PropertyFinancials(
        purchase_price_cents=from_dollars(price),
        jurisdiction=jurisdiction,
        property_kind=kind,
    )


def line(result, key: str) -> int:
    matches = [line.amount_cents for line in result.value.lines if line.key == key]
    assert matches, f"no {key} line; got {[x.key for x in result.value.lines]}"
    return matches[0]


def costs(
    price: str,
    *,
    jurisdiction: str = "ON/Toronto",
    first_time: bool = True,
    as_of: date = TODAY,
    kind: PropertyKind = PropertyKind.DETACHED,
    residency: ResidencyStatus = ResidencyStatus.CITIZEN_OR_PR,
):
    return compute_closing_costs(
        property_=prop(price, jurisdiction=jurisdiction, kind=kind),
        buyer=replace(buyer(down="200000", first_time=first_time), residency_status=residency),
        mortgage=NO_MORTGAGE,
        rules=RULES,
        as_of=as_of,
    )


class TestMarginalBrackets:
    def test_a_single_bracket_is_a_flat_rate(self):
        assert marginal_tax(from_dollars("50000"), [[0, "0.005"]]) == from_dollars("250")

    def test_each_rate_applies_only_to_its_own_portion(self):
        brackets = [[0, "0.005"], [5_500_000, "0.01"]]
        # 55,000 * 0.5% + 45,000 * 1% = 275 + 450
        assert marginal_tax(from_dollars("100000"), brackets) == from_dollars("725")

    def test_exactly_on_a_boundary_stays_in_the_lower_band(self):
        brackets = [[0, "0.005"], [5_500_000, "0.01"]]
        assert marginal_tax(from_dollars("55000"), brackets) == from_dollars("275")


class TestOntarioLandTransferTax:
    @pytest.mark.parametrize(
        ("price", "expected"),
        [
            # 275 + 1,950 + 2,250 + 2% of the excess over 400,000
            ("400000", "4475"),
            ("500000", "6475"),
            ("850000", "13475"),
            ("1500000", "26475"),
            # The 2.5% band above $2M applies to one or two single family residences.
            ("2000000", "36475"),
            ("3000000", "61475"),
        ],
    )
    def test_brackets(self, price, expected):
        assert line(costs(price, first_time=False), "ltt_ontario") == from_dollars(expected)

    def test_the_two_and_a_half_percent_band_is_single_family_only(self):
        sfr = line(costs("3000000", first_time=False), "ltt_ontario")
        other = line(costs("3000000", first_time=False, kind=PropertyKind.OTHER), "ltt_ontario")
        # 1,000,000 above $2M, taxed at 2.5% instead of 2.0%
        assert sfr - other == from_dollars("5000")


class TestTorontoMunicipalLandTransferTax:
    def test_toronto_pays_twice(self):
        toronto = costs("850000", first_time=False)
        oakville = costs("850000", jurisdiction="ON/Oakville", first_time=False)
        assert line(toronto, "mltt") == line(toronto, "ltt_ontario")
        assert not [x for x in oakville.value.lines if x.key == "mltt"]

    def test_outside_toronto_there_is_simply_no_municipal_tax(self):
        """Not an error — the rule does not resolve for that jurisdiction and the
        buyer correctly pays provincial tax alone."""
        result = costs("850000", jurisdiction="ON/Ottawa", first_time=False)
        keys = {x.key for x in result.value.lines}
        assert "ltt_ontario" in keys
        assert "mltt" not in keys and "mltt_admin_fee" not in keys

    @pytest.mark.parametrize(
        ("price", "expected"),
        [
            ("2000000", "36475"),
            # 3,000,000: adds 500,000 at 2.5% on top of the 2M figure
            ("3000000", "61475"),
            # 4,000,000: the first luxury band, 1,000,000 at 4.40%
            ("4000000", "105475"),
            # 5,000,000: + 1,000,000 at 5.45%
            ("5000000", "159975"),
        ],
    )
    def test_the_luxury_bands_apply_from_april_2026(self, price, expected):
        assert line(costs(price, first_time=False), "mltt") == from_dollars(expected)

    def test_a_march_closing_reproduces_march(self):
        """The registry's whole reason for existing.

        Before 1 April 2026 the top Toronto band was 2.5%, so a $4M house paid
        $86,475. Under the luxury bands the million above $3M is taxed at 4.40%
        instead, taking it to $105,475 — $19,000 more, for the same house, decided
        by the closing date. A hardcoded bracket table would still be quoting March.
        """
        before = line(costs("4000000", first_time=False, as_of=BEFORE_LUXURY), "mltt")
        after = line(costs("4000000", first_time=False, as_of=TODAY), "mltt")
        assert before == from_dollars("86475")
        assert after == from_dollars("105475")
        assert after - before == from_dollars("19000")

    def test_the_administration_fee_carries_hst(self):
        assert line(costs("850000", first_time=False), "mltt_admin_fee") == from_dollars("115.89")


class TestFirstTimeBuyerRebates:
    def test_both_rebates_are_capped(self):
        result = costs("850000", first_time=True)
        assert line(result, "ltt_ontario_ftb_refund") == -from_dollars("4000")
        assert line(result, "mltt_ftb_rebate") == -from_dollars("4475")

    def test_a_cheap_purchase_gets_only_what_it_owes(self):
        """At $300,000 the provincial tax is $2,975, so the refund is $2,975 — not
        the $4,000 cap. Modelling the rebate as an exemption threshold would hand
        this buyer $1,025 they never paid."""
        result = costs("300000", first_time=True)
        assert line(result, "ltt_ontario") == from_dollars("2975")
        assert line(result, "ltt_ontario_ftb_refund") == -from_dollars("2975")

    def test_a_repeat_buyer_gets_nothing(self):
        keys = {x.key for x in costs("850000", first_time=False).value.lines}
        assert "ltt_ontario_ftb_refund" not in keys
        assert "mltt_ftb_rebate" not in keys


class TestNonResidentSpeculationTax:
    def test_a_foreign_national_in_toronto_pays_thirty_five_percent(self):
        result = costs("850000", first_time=False, residency=ResidencyStatus.FOREIGN_NATIONAL)
        assert line(result, "nrst") == from_dollars("212500")
        assert line(result, "mnrst") == from_dollars("85000")

    def test_unknown_residency_is_declared_rather_than_assumed(self):
        """25% of the price is far too large a number to assume in either direction."""
        result = costs("850000", first_time=False, residency=ResidencyStatus.UNKNOWN)
        assert not [x for x in result.value.lines if x.key == "nrst"]
        assert any(a.key == "residency_status" for a in result.assumptions)


class TestTotals:
    def test_the_total_is_the_sum_of_the_lines(self):
        result = costs("850000", first_time=True)
        assert result.value.total_cents == sum(x.amount_cents for x in result.value.lines)

    def test_rebates_reduce_the_total(self):
        first_time = costs("850000", first_time=True).value.total_cents
        repeat = costs("850000", first_time=False).value.total_cents
        assert repeat - first_time == from_dollars("8475")

    def test_a_condo_is_charged_for_a_status_certificate(self):
        keys = {x.key for x in costs("850000", kind=PropertyKind.CONDO_APARTMENT).value.lines}
        assert "status_certificate" in keys
        assert "status_certificate" not in {x.key for x in costs("850000").value.lines}

    def test_every_estimated_line_is_flagged_as_one(self):
        result = costs("850000", first_time=True)
        estimated = {x.key for x in result.value.lines if x.is_estimate}
        assert "legal_fees" in estimated and "moving" in estimated
        # Statutory amounts are never estimates.
        assert "ltt_ontario" not in estimated and "mltt" not in estimated
