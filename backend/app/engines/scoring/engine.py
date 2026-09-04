"""Aggregation: subscores and weights into one Buy Score, or into a refusal.

Two behaviours carry the product's honesty, and both live here.

**A subscore that could not be computed is dropped, not zeroed.** Its weight is
redistributed proportionally across whatever remains and the analysis's confidence
falls. Zeroing an unknown is fabrication pointing the other way, and it is how most
scores on the internet quietly punish sparse data.

**Past a threshold there is no score at all.** When more than 35% of weight has
been redistributed, ``buy_score`` is ``None`` with a stated reason, while every
subscore and every dollar figure still renders. A composite assembled from a third
of nothing is not a number to put in front of someone about to spend $850,000.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.engines.scoring.contracts import (
    BASE_WEIGHTS,
    MAX_MODIFIER,
    MAX_REDISTRIBUTED_WEIGHT,
    MIN_MODIFIER,
    SCORING_MODEL_VERSION,
    BuyScore,
    Component,
    Subscore,
)

ZERO = Decimal(0)
ONE = Decimal(1)


def clamp_modifier(value: Decimal) -> Decimal:
    """Keep a preference dial from turning the composite into one component."""
    return max(MIN_MODIFIER, min(MAX_MODIFIER, value))


def aggregate(
    *,
    subscores: tuple[Subscore, ...],
    modifiers: dict[Component, Decimal] | None = None,
) -> BuyScore:
    """Combine subscores into a Buy Score, or decline to.

    Pure: no clock, no randomness, no I/O. The same subscores and modifiers under
    the same ``SCORING_MODEL_VERSION`` produce byte-identical output, which is the
    contract ``property_analyses.inputs_hash`` depends on.
    """
    if not subscores:
        raise ValueError("aggregate() needs at least one subscore")

    seen = [s.component for s in subscores]
    if len(seen) != len(set(seen)):
        raise ValueError(f"duplicate components: {seen}")

    modifiers = modifiers or {}
    available = [s for s in subscores if s.available]

    # Weight actually in play: base weight scaled by the household's own priorities.
    raw_weights: dict[Component, Decimal] = {}
    for subscore in available:
        modifier = clamp_modifier(modifiers.get(subscore.component, ONE))
        raw_weights[subscore.component] = subscore.base_weight * modifier

    lost = sum(
        (s.base_weight for s in subscores if not s.available),
        start=ZERO,
    )
    total_raw = sum(raw_weights.values(), start=ZERO)

    rebuilt: list[Subscore] = []
    weights_applied: dict[Component, Decimal] = {}
    weighted_total = ZERO
    confidence_total = ZERO

    for subscore in subscores:
        if not subscore.available:
            rebuilt.append(
                Subscore(
                    component=subscore.component,
                    available=False,
                    score=None,
                    confidence=ZERO,
                    base_weight=subscore.base_weight,
                    effective_weight=ZERO,
                    contribution=ZERO,
                    unavailable_reason=subscore.unavailable_reason,
                    factors=subscore.factors,
                )
            )
            continue

        effective = (
            (raw_weights[subscore.component] / total_raw).quantize(Decimal("0.0001"))
            if total_raw
            else ZERO
        )
        score = subscore.score or ZERO
        contribution = (score * effective).quantize(Decimal("0.0001"))
        weighted_total += contribution
        confidence_total += effective * subscore.confidence
        weights_applied[subscore.component] = effective
        rebuilt.append(
            Subscore(
                component=subscore.component,
                available=True,
                score=score,
                confidence=subscore.confidence,
                base_weight=subscore.base_weight,
                effective_weight=effective,
                contribution=contribution,
                factors=subscore.factors,
            )
        )

    withheld: str | None = None
    if lost > MAX_REDISTRIBUTED_WEIGHT:
        missing = ", ".join(
            s.component.value.replace("_", " ") for s in subscores if not s.available
        )
        withheld = (
            f"{lost:.0%} of the scoring weight could not be computed ({missing}), which is "
            f"more than the {MAX_REDISTRIBUTED_WEIGHT:.0%} limit. The subscores below still "
            "stand on their own."
        )

    buy_score = (
        None
        if withheld
        else int(
            max(ZERO, min(Decimal(100), weighted_total)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
    )

    # Missing weight is a confidence penalty even below the withholding threshold:
    # a score built on 70% of the model is not as trustworthy as one built on all
    # of it, and the number the user sees should say so.
    confidence = (confidence_total * (ONE - lost)).quantize(Decimal("0.001"))

    return BuyScore(
        buy_score=buy_score,
        withheld_reason=withheld,
        confidence=max(ZERO, min(ONE, confidence)),
        subscores=tuple(rebuilt),
        weights_applied=weights_applied,
        redistributed_weight=lost,
        scoring_model_version=SCORING_MODEL_VERSION,
    )


def modifiers_for(
    *,
    goal: str | None,
    horizon: str | None,
    risk_posture: str | None,
    has_children: bool | None,
    schools_importance: int | None,
    budget_pressure: bool,
) -> dict[Component, Decimal]:
    """Turn a buyer profile into weight modifiers (``SCORING_MODEL.md`` §2).

    This is why two households can read different Buy Scores for the same house and
    both be right: an investor and a family are not asking the same question.
    """
    modifiers: dict[Component, Decimal] = {}

    def bump(component: Component, factor: str) -> None:
        modifiers[component] = modifiers.get(component, ONE) * Decimal(factor)

    if goal == "investment":
        bump(Component.INVESTMENT, "1.75")
        bump(Component.PERSONAL_FIT, "0.6")
    elif goal == "primary_residence":
        bump(Component.PERSONAL_FIT, "1.2")
        bump(Component.INVESTMENT, "0.7")

    if has_children and (schools_importance or 0) >= 4:
        bump(Component.LOCATION, "1.4")
        bump(Component.PROPERTY_QUALITY, "1.15")

    if horizon == "under_3":
        bump(Component.VALUE, "1.3")
        bump(Component.INVESTMENT, "1.2")
        bump(Component.RISK, "1.2")
    elif horizon == "over_10":
        bump(Component.VALUE, "0.85")
        bump(Component.PERSONAL_FIT, "1.2")

    if budget_pressure:
        bump(Component.AFFORDABILITY, "1.4")

    if risk_posture == "conservative":
        bump(Component.RISK, "1.4")
    elif risk_posture == "aggressive":
        bump(Component.RISK, "0.7")

    return {component: clamp_modifier(value) for component, value in modifiers.items()}


def unavailable(component: Component, reason: str) -> Subscore:
    """A component we could not compute, with the reason the user will read."""
    return Subscore(
        component=component,
        available=False,
        score=None,
        confidence=ZERO,
        base_weight=BASE_WEIGHTS[component],
        effective_weight=ZERO,
        contribution=ZERO,
        unavailable_reason=reason,
    )
