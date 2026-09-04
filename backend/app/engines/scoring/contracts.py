"""The scoring engine's contract, including the two rules that make it honest.

**A subscore that cannot be computed is dropped, not zeroed.** Its weight is
redistributed across the rest and the analysis's confidence falls. Scoring an
unknown as zero would be fabrication pointing the other way, and it is how most
"scores" on the internet quietly punish sparse data.

**Past a threshold, there is no score at all.** When more than
:data:`MAX_REDISTRIBUTED_WEIGHT` of the weight has been redistributed, the Buy
Score is withheld — ``buy_score`` is ``None`` and ``withheld_reason`` says why —
while every subscore and every dollar figure still renders. A composite built
from a third of nothing is not a number worth showing someone who is about to
spend $850,000.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

MAX_REDISTRIBUTED_WEIGHT = Decimal("0.35")
SCORING_MODEL_VERSION = "0.1.0"


class Component(StrEnum):
    AFFORDABILITY = "affordability"
    VALUE = "value"
    PERSONAL_FIT = "personal_fit"
    LOCATION = "location"
    PROPERTY_QUALITY = "property_quality"
    INVESTMENT = "investment"
    RISK = "risk"
    MARKET = "market"


BASE_WEIGHTS: dict[Component, Decimal] = {
    Component.AFFORDABILITY: Decimal("0.25"),
    Component.VALUE: Decimal("0.20"),
    Component.PERSONAL_FIT: Decimal("0.15"),
    Component.LOCATION: Decimal("0.10"),
    Component.PROPERTY_QUALITY: Decimal("0.10"),
    Component.INVESTMENT: Decimal("0.08"),
    Component.RISK: Decimal("0.07"),
    Component.MARKET: Decimal("0.05"),
}

#: User modifiers are clamped before renormalization so that no profile can turn
#: the Buy Score into a single component wearing a composite's clothes.
MIN_MODIFIER = Decimal("0.5")
MAX_MODIFIER = Decimal("2.0")


class Direction(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class Factor:
    """One sentence the UI may render and the AI layer may explain.

    If a factor is not here, it may not appear in an explanation — the numeric
    guard on the AI output has a sibling rule for claims.
    """

    component: Component
    direction: Direction
    magnitude: Decimal
    sentence: str
    provenance_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Subscore:
    component: Component
    available: bool
    score: Decimal | None
    """0–100, or None when the component could not be computed."""

    confidence: Decimal
    base_weight: Decimal
    effective_weight: Decimal
    contribution: Decimal
    unavailable_reason: str | None = None
    factors: tuple[Factor, ...] = ()

    def __post_init__(self) -> None:
        if self.available and self.score is None:
            raise ValueError(f"{self.component}: available subscore must carry a score")
        if not self.available and not self.unavailable_reason:
            raise ValueError(f"{self.component}: unavailable subscore must carry a reason")


@dataclass(frozen=True, slots=True)
class BuyScore:
    buy_score: int | None
    """None when withheld. The API field is nullable for exactly this reason."""

    withheld_reason: str | None
    confidence: Decimal
    subscores: tuple[Subscore, ...]
    weights_applied: dict[Component, Decimal]
    redistributed_weight: Decimal
    scoring_model_version: str = SCORING_MODEL_VERSION

    def __post_init__(self) -> None:
        if self.buy_score is None and not self.withheld_reason:
            raise ValueError("a withheld score must explain why")
        if self.buy_score is not None and not 0 <= self.buy_score <= 100:
            raise ValueError(f"buy_score out of range: {self.buy_score}")


class ScoringEngine(Protocol):
    """Pure, versioned, reproducible.

    The same inputs under the same ``scoring_model_version`` and the same rule set
    must produce the same score, byte for byte. There is a test that asserts it,
    and it is the reason nothing in here reads a clock or a random source.
    """

    def score(
        self,
        *,
        subscores: tuple[Subscore, ...],
        modifiers: dict[Component, Decimal],
    ) -> BuyScore: ...
