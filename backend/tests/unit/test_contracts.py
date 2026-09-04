"""The invariants the contracts refuse to let an implementer break."""

from decimal import Decimal

import pytest

from app.core.money import cents
from app.engines.base import TraceBuilder
from app.engines.scoring.contracts import (
    BASE_WEIGHTS,
    MAX_REDISTRIBUTED_WEIGHT,
    BuyScore,
    Component,
    Subscore,
)
from app.engines.valuation.contracts import (
    FairValueRange,
    RiskCategory,
    RiskFlag,
    RiskSeverity,
    RiskStatus,
    ValuationBasis,
)


def test_base_weights_sum_to_one():
    assert sum(BASE_WEIGHTS.values()) == Decimal("1.00")


def test_a_withheld_score_must_explain_itself():
    with pytest.raises(ValueError, match="withheld"):
        BuyScore(
            buy_score=None,
            withheld_reason=None,
            confidence=Decimal("0.4"),
            subscores=(),
            weights_applied={},
            redistributed_weight=Decimal("0.4"),
        )


def test_withholding_is_expressible_and_keeps_the_subscores():
    subscore = Subscore(
        component=Component.AFFORDABILITY,
        available=True,
        score=Decimal("91"),
        confidence=Decimal("0.95"),
        base_weight=Decimal("0.25"),
        effective_weight=Decimal("0.38"),
        contribution=Decimal("34.6"),
    )
    score = BuyScore(
        buy_score=None,
        withheld_reason="more than 35% of scoring weight was unavailable",
        confidence=Decimal("0.41"),
        subscores=(subscore,),
        weights_applied={Component.AFFORDABILITY: Decimal("0.38")},
        redistributed_weight=MAX_REDISTRIBUTED_WEIGHT + Decimal("0.05"),
    )
    assert score.buy_score is None
    assert score.subscores[0].score == Decimal("91")


def test_an_unavailable_subscore_must_carry_a_reason():
    with pytest.raises(ValueError, match="reason"):
        Subscore(
            component=Component.VALUE,
            available=False,
            score=None,
            confidence=Decimal("0"),
            base_weight=Decimal("0.20"),
            effective_weight=Decimal("0"),
            contribution=Decimal("0"),
        )


def test_unknown_risk_does_not_touch_the_score():
    unknown = RiskFlag(
        category=RiskCategory.FLOOD,
        status=RiskStatus.UNKNOWN,
        severity=RiskSeverity.MEDIUM,
        evidence="property lies outside TRCA mapped coverage",
        explanation="We could not determine flood exposure at this address.",
        recommended_action="Ask the conservation authority before waiving conditions.",
        source_key="src_trca",
    )
    confirmed = RiskFlag(
        category=RiskCategory.FLOOD,
        status=RiskStatus.CONFIRMED,
        severity=RiskSeverity.HIGH,
        evidence="inside the TRCA regulatory flood line",
        explanation="The property intersects a mapped flood plain.",
        recommended_action="Confirm insurability before removing conditions.",
        source_key="src_trca",
    )
    assert unknown.affects_score is False
    assert confirmed.affects_score is True


def test_fair_value_is_always_a_range():
    with pytest.raises(ValueError, match="below low"):
        FairValueRange(
            low_cents=cents(84_500_000),
            high_cents=cents(82_000_000),
            basis=ValuationBasis.MARKET_BENCHMARK_ONLY,
            confidence=Decimal("0.45"),
            note="x",
        )


def test_trace_builder_records_the_working_as_it_goes():
    trace = TraceBuilder()
    principal = trace.step(
        "mortgage principal",
        "price - down_payment",
        {"price": 85_000_000, "down_payment": 12_000_000},
        73_000_000,
        unit="cents",
    )
    trace.assume("maintenance_reserve_pct", "0.01", "1% of value per year, industry convention")
    result = trace.finish(principal, confidence=0.9)

    assert result.value == 73_000_000
    assert result.is_complete
    assert result.explain() == [
        "mortgage principal: price - down_payment = 73000000",
    ]
    assert result.assumptions[0].key == "maintenance_reserve_pct"
