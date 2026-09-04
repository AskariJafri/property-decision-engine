from datetime import date

import pytest

from app.engines.rules import Rule, RuleNotFoundError, RuleSet, Verification

ON_LTT = Rule(
    jurisdiction="ON",
    name="ltt.brackets",
    value=[[0, "0.005"], [5_500_000, "0.01"]],
    effective_from=date(2017, 1, 1),
    source_url="https://www.ontario.ca/document/land-transfer-tax/calculating-land-transfer-tax",
    verification=Verification.PRIMARY,
)

MLTT_2025 = Rule(
    jurisdiction="ON/Toronto",
    name="mltt.brackets",
    value="pre-luxury",
    effective_from=date(2023, 1, 1),
    effective_to=date(2026, 3, 31),
    source_url="https://www.toronto.ca/",
    verification=Verification.PRIMARY,
)

MLTT_2026 = Rule(
    jurisdiction="ON/Toronto",
    name="mltt.brackets",
    value="luxury-bands",
    effective_from=date(2026, 4, 1),
    source_url="https://www.toronto.ca/",
    verification=Verification.PRIMARY,
    version=2,
)

RULES = RuleSet(label="test.1", rules=(ON_LTT, MLTT_2025, MLTT_2026))


def test_unverified_rule_cannot_be_active():
    # A number we could not confirm must never reach a calculation someone spends money on.
    with pytest.raises(ValueError, match="unverified"):
        Rule(
            jurisdiction="CA",
            name="insured.amortization_surcharge",
            value="0.002",
            effective_from=date(2024, 12, 15),
            source_url="https://example.invalid",
            verification=Verification.UNVERIFIED,
            active=True,
        )


def test_unverified_rule_may_exist_while_inactive():
    rule = Rule(
        jurisdiction="CA",
        name="insured.amortization_surcharge",
        value="0.002",
        effective_from=date(2024, 12, 15),
        source_url="https://example.invalid",
        verification=Verification.UNVERIFIED,
        active=False,
    )
    assert (
        RuleSet("t", (rule,)).find("CA", "insured.amortization_surcharge", as_of=date.today())
        is None
    )


def test_as_of_picks_the_bands_in_force_that_day():
    # The April 2026 luxury change is the reason this registry exists.
    assert RULES.get("ON/Toronto", "mltt.brackets", as_of=date(2026, 3, 31)).value == "pre-luxury"
    assert RULES.get("ON/Toronto", "mltt.brackets", as_of=date(2026, 4, 1)).value == "luxury-bands"


def test_jurisdiction_falls_back_to_the_province():
    rule = RULES.get("ON/Toronto", "ltt.brackets", as_of=date(2026, 9, 4))
    assert rule.jurisdiction == "ON"


def test_municipal_rule_does_not_leak_to_other_municipalities():
    # Outside Toronto there is no MLTT, and that is a normal answer, not a failure.
    assert RULES.find("ON/Ottawa", "mltt.brackets", as_of=date(2026, 9, 4)) is None
    with pytest.raises(RuleNotFoundError):
        RULES.get("ON/Ottawa", "mltt.brackets", as_of=date(2026, 9, 4))


def test_effective_range_is_validated():
    with pytest.raises(ValueError, match="effective_to"):
        Rule(
            jurisdiction="ON",
            name="x",
            value=1,
            effective_from=date(2026, 5, 1),
            effective_to=date(2026, 4, 1),
            source_url="https://example.invalid",
            verification=Verification.PRIMARY,
        )
