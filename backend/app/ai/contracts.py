"""The AI layer's contract: bounded judgements in, capped adjustments out.

ADR 0004. A model contributes to the decision by producing **typed judgements**
that the deterministic engines consume, not by adjusting a score after the fact.
Three properties make that safe enough to put in front of someone spending most
of their net worth:

**Pinned, not regenerated.** Temperature 0 is not determinism — model versions
shift, quantisations differ, hardware changes the margin. So a judgement is
computed once, stored with its model id, prompt hash and sampling parameters, and
replayed. The score stays reproducible because the model is not in the loop at
score time.

**Capped.** Each judgement type declares the most it may move its subscore. A
completely wrong ``condition_signal`` costs a couple of points on the Buy Score,
carries a visible AI-inferred label, and cannot flip a recommendation.

**Evidence-bearing.** Every item quotes the span it came from. A judgement with no
supporting text is dropped rather than trusted, which is the difference between
reading a listing and imagining one.

The provider speaks the OpenAI-compatible chat shape, so local Ollama today and
free hosted tiers later differ by a base URL and a model name.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from app.engines.scoring.contracts import CappedAdjustment, Component

JUDGEMENT_SCHEMA_VERSION = "0.1.0"

__all__ = [  # CappedAdjustment is re-exported: defined in the engine that consumes it
    "CappedAdjustment",
    "Evidence",
    "Judgement",
    "JudgementItem",
    "JudgementType",
    "LlmProvider",
    "LlmUnavailableError",
    "apply_judgement",
]


class JudgementType(StrEnum):
    CONDITION_SIGNAL = "condition_signal"
    """Renovation recency, deferred maintenance, age-of-systems, 'as-is' framing."""

    LISTING_RED_FLAGS = "listing_red_flags"
    """Phrases that map to investigation items. Always POTENTIAL, never CONFIRMED."""

    OMISSION_SIGNALS = "omission_signals"
    """What a listing conspicuously does not say. Generates questions, moves nothing."""

    PREFERENCE_INTERPRETATION = "preference_interpretation"
    """Free-text wants into structure. Becomes USER_ASSERTED once the user confirms."""

    DECISION_REVIEW = "decision_review"
    """Internal inconsistencies in a finished analysis. Surfaces a flag, moves nothing."""


#: Maximum points each judgement type may move its subscore, before weighting.
#: Stored on the row as well (``ai_judgements.influence_cap``) so an old analysis
#: is explained by the cap that actually applied to it, not today's constant.
INFLUENCE_CAPS: dict[JudgementType, Decimal] = {
    JudgementType.CONDITION_SIGNAL: Decimal("8"),
    JudgementType.LISTING_RED_FLAGS: Decimal("6"),
    JudgementType.OMISSION_SIGNALS: Decimal("0"),
    JudgementType.PREFERENCE_INTERPRETATION: Decimal("0"),
    JudgementType.DECISION_REVIEW: Decimal("0"),
}

#: Which subscore each type may touch. A type absent here influences no score.
TARGET_COMPONENT: dict[JudgementType, Component | None] = {
    JudgementType.CONDITION_SIGNAL: Component.PROPERTY_QUALITY,
    JudgementType.LISTING_RED_FLAGS: Component.RISK,
    JudgementType.OMISSION_SIGNALS: None,
    JudgementType.PREFERENCE_INTERPRETATION: None,
    JudgementType.DECISION_REVIEW: None,
}


class LlmUnavailableError(RuntimeError):
    """No model configured, the model is down, or its output failed validation.

    Never fatal to an analysis. The caller records the judgement as unavailable
    with this reason, its contribution drops to zero, weight redistributes and
    confidence falls — the same degradation every other provider gets.
    """


@dataclass(frozen=True, slots=True)
class Evidence:
    """The span a judgement item came from. Required."""

    quote: str
    source_ref: str
    """Which document and where: ``property_sources/<id>#p3``."""


@dataclass(frozen=True, slots=True)
class JudgementItem:
    key: str
    """``furnace_original``, ``sold_as_is``, ``roof_age_unstated``."""

    direction: int
    """-1 concerning, 0 neutral, +1 reassuring."""

    weight: Decimal
    """0–1, this item's share of the type's influence cap."""

    statement: str
    evidence: tuple[Evidence, ...]

    def __post_init__(self) -> None:
        if self.direction not in (-1, 0, 1):
            raise ValueError(f"direction must be -1, 0 or 1, got {self.direction}")
        if not Decimal(0) <= self.weight <= Decimal(1):
            raise ValueError(f"weight must be in [0, 1], got {self.weight}")
        if not self.evidence:
            raise ValueError(f"{self.key}: a judgement item without evidence is a guess")


@dataclass(frozen=True, slots=True)
class Judgement:
    """One pinned model judgement, ready to be stored and replayed."""

    judgement_type: JudgementType
    items: tuple[JudgementItem, ...]
    confidence: Decimal
    model_id: str
    """The exact tag — ``llama3.1:8b-instruct-q4_K_M``, never ``llama3``."""

    prompt_hash: str
    sampling: dict[str, object]
    schema_version: str = JUDGEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.confidence <= Decimal(1):
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")

    @property
    def influence_cap(self) -> Decimal:
        return INFLUENCE_CAPS[self.judgement_type]

    @property
    def target_component(self) -> Component | None:
        return TARGET_COMPONENT[self.judgement_type]


def apply_judgement(judgement: Judgement) -> CappedAdjustment | None:
    """Turn a judgement into a bounded subscore adjustment. Pure and deterministic.

    The raw signal is the confidence-weighted sum of item directions, scaled by the
    type's cap. Then it is clamped to the cap, so no arithmetic path — however the
    weights are distributed, however confident the model claims to be — can exceed
    the bound the ADR promises.
    """
    component = judgement.target_component
    if component is None:
        return None

    cap = judgement.influence_cap
    if cap == 0:
        return None

    signal = sum(
        (item.weight * Decimal(item.direction) for item in judgement.items), start=Decimal(0)
    )
    raw = signal * judgement.confidence * cap
    applied = max(-cap, min(cap, raw))
    return CappedAdjustment(
        component=component,
        raw_adjustment=raw,
        applied_adjustment=applied,
        capped=applied != raw,
    )


class LlmProvider(Protocol):
    """OpenAI-compatible chat completion, so local and hosted differ by a URL.

    Implementations must pin sampling (temperature 0, a fixed seed where the
    backend honours one) and return the model identifier they actually used, not
    the alias that was requested.
    """

    @property
    def model_id(self) -> str: ...

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, object],
        max_tokens: int = 1024,
    ) -> dict[str, object]:
        """Return validated JSON, or raise :class:`LlmUnavailableError`."""
