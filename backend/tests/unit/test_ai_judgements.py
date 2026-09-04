"""ADR 0004's guarantees, asserted rather than promised."""

from decimal import Decimal

import pytest

from app.ai.contracts import (
    INFLUENCE_CAPS,
    Evidence,
    Judgement,
    JudgementItem,
    JudgementType,
    apply_judgement,
)
from app.engines.scoring.contracts import Component


def _item(key: str, direction: int, weight: str) -> JudgementItem:
    return JudgementItem(
        key=key,
        direction=direction,
        weight=Decimal(weight),
        statement=f"{key} noted in the listing",
        evidence=(Evidence(quote="furnace original to the home", source_ref="src#p2"),),
    )


def _judgement(
    type_: JudgementType, items: tuple[JudgementItem, ...], confidence: str = "1"
) -> Judgement:
    return Judgement(
        judgement_type=type_,
        items=items,
        confidence=Decimal(confidence),
        model_id="llama3.1:8b-instruct-q4_K_M",
        prompt_hash="a" * 64,
        sampling={"temperature": 0, "seed": 7},
    )


def test_an_item_without_evidence_is_a_guess_and_is_refused():
    with pytest.raises(ValueError, match="without evidence"):
        JudgementItem(
            key="furnace_original",
            direction=-1,
            weight=Decimal("1"),
            statement="the furnace is original",
            evidence=(),
        )


def test_a_judgement_cannot_exceed_its_cap_however_hard_it_tries():
    # Ten maximally-weighted concerning items at full confidence: the cap still holds.
    items = tuple(_item(f"issue_{i}", -1, "1") for i in range(10))
    adjustment = apply_judgement(_judgement(JudgementType.CONDITION_SIGNAL, items))
    assert adjustment is not None
    assert adjustment.applied_adjustment == -INFLUENCE_CAPS[JudgementType.CONDITION_SIGNAL]
    assert adjustment.capped is True


def test_confidence_scales_the_adjustment():
    items = (_item("furnace_original", -1, "0.5"),)
    full = apply_judgement(_judgement(JudgementType.CONDITION_SIGNAL, items, confidence="1"))
    half = apply_judgement(_judgement(JudgementType.CONDITION_SIGNAL, items, confidence="0.5"))
    assert full is not None and half is not None
    assert half.applied_adjustment == full.applied_adjustment / 2
    assert full.capped is False


def test_condition_signals_land_on_property_quality():
    adjustment = apply_judgement(
        _judgement(JudgementType.CONDITION_SIGNAL, (_item("reno_2024", 1, "0.4"),))
    )
    assert adjustment is not None
    assert adjustment.component is Component.PROPERTY_QUALITY
    assert adjustment.applied_adjustment > 0


def test_narrative_judgement_types_move_nothing():
    # Omissions generate questions and decision_review surfaces a flag. Neither
    # touches a score, and the caps table is what enforces that.
    for type_ in (
        JudgementType.OMISSION_SIGNALS,
        JudgementType.PREFERENCE_INTERPRETATION,
        JudgementType.DECISION_REVIEW,
    ):
        assert apply_judgement(_judgement(type_, (_item("x", -1, "1"),))) is None


def test_every_judgement_type_declares_a_cap_and_a_target():
    from app.ai.contracts import TARGET_COMPONENT

    for type_ in JudgementType:
        assert type_ in INFLUENCE_CAPS, f"{type_} has no declared cap"
        assert type_ in TARGET_COMPONENT, f"{type_} has no declared target"
        if TARGET_COMPONENT[type_] is None:
            assert INFLUENCE_CAPS[type_] == 0, f"{type_} targets nothing but claims influence"


def test_the_same_pinned_judgement_always_produces_the_same_adjustment():
    # The reproducibility contract: the model is not in the loop at score time.
    items = (_item("furnace_original", -1, "0.6"), _item("roof_2019", 1, "0.3"))
    first = apply_judgement(_judgement(JudgementType.CONDITION_SIGNAL, items, confidence="0.8"))
    second = apply_judgement(_judgement(JudgementType.CONDITION_SIGNAL, items, confidence="0.8"))
    assert first == second
