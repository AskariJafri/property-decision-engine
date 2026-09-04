"""Where a value came from, and how much to trust it.

Every number this product shows a user is one of six things, and the difference
matters more here than in most software: a user is about to spend most of their
net worth on the strength of it. ``SourceClass`` is that distinction made
explicit, and it travels with the value from the provider adapter through the
engines to the JSON field, because a label that is applied at the presentation
layer is a label that will eventually be applied wrongly.

The seventh case is the important one. :class:`Fact` can hold *nothing* — an
explicit ``UNAVAILABLE`` with a required reason. That is not an error state and
not an empty string; it is a value the UI renders as "Data unavailable", and the
constructor refuses to build one without saying why.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self


class SourceClass(StrEnum):
    """How a value came to exist. Ordered loosely by how much weight it deserves."""

    VERIFIED = "verified"
    """Read from an authoritative source: a by-law, a government dataset, a registry."""

    CALCULATED = "calculated"
    """Computed deterministically by our own engines from other facts."""

    ESTIMATED = "estimated"
    """Derived from a model or a benchmark, with a stated method."""

    ASSUMED = "assumed"
    """A default we chose because nothing better was available. Always visible to the user."""

    AI_INFERRED = "ai_inferred"
    """Extracted or inferred by a language model. Never accepted without validation."""

    USER_ASSERTED = "user_asserted"
    """The user told us. Trusted, but flagged when it contradicts another source."""

    UNAVAILABLE = "unavailable"
    """We looked and could not determine it. Requires a reason."""


#: Confidence multipliers by source class, used by the scoring engine's
#: ``source_quality`` term (SCORING_MODEL.md §8).
SOURCE_QUALITY: dict[SourceClass, float] = {
    SourceClass.VERIFIED: 1.0,
    SourceClass.CALCULATED: 1.0,
    SourceClass.ESTIMATED: 0.7,
    SourceClass.ASSUMED: 0.6,
    SourceClass.AI_INFERRED: 0.5,
    SourceClass.USER_ASSERTED: 0.65,
    SourceClass.UNAVAILABLE: 0.0,
}


@dataclass(frozen=True, slots=True)
class Provenance:
    """The audit record for one fact."""

    source_key: str
    """Key into ``data_sources`` — the provider, not a free-text description."""

    source_class: SourceClass
    retrieved_at: datetime
    effective_at: datetime | None = None
    """When the value was *true*: the by-law year, the assessment year, the sale date."""

    confidence: float = 1.0
    expires_at: datetime | None = None
    """Set only where a provider's licence caps retention. The sweeper honours it."""

    unavailable_reason: str | None = None
    source_url: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if self.source_class is SourceClass.UNAVAILABLE and not self.unavailable_reason:
            raise ValueError("an unavailable fact must carry a reason")
        for field_name in ("retrieved_at", "effective_at", "expires_at"):
            value = getattr(self, field_name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Fact[T]:
    """A value that knows where it came from, or an explicit absence.

    Engines take Facts and return Facts. That is what makes it structurally hard
    to lose provenance halfway through a calculation: there is no unwrapped
    number to pass around.
    """

    value: T | None
    provenance: Provenance
    unit: str | None = None

    @property
    def is_available(self) -> bool:
        return self.provenance.source_class is not SourceClass.UNAVAILABLE

    @property
    def quality(self) -> float:
        """Confidence weighted by the trustworthiness of the class it came from."""
        return self.provenance.confidence * SOURCE_QUALITY[self.provenance.source_class]

    def require(self) -> T:
        """Unwrap, or raise. For call sites that genuinely cannot proceed without it."""
        if self.value is None:
            raise ValueError(f"required value is unavailable: {self.provenance.unavailable_reason}")
        return self.value

    def or_else(self, default: T) -> T:
        """Unwrap, or fall back. The caller is responsible for labelling the result ASSUMED."""
        return default if self.value is None else self.value

    @classmethod
    def unavailable(cls, reason: str, *, source_key: str = "none") -> Self:
        """The honest answer, as a first-class value."""
        return cls(
            value=None,
            provenance=Provenance(
                source_key=source_key,
                source_class=SourceClass.UNAVAILABLE,
                retrieved_at=datetime.now(UTC),
                confidence=0.0,
                unavailable_reason=reason,
            ),
        )

    @classmethod
    def calculated(
        cls,
        value: T,
        *,
        source_key: str = "engine",
        confidence: float = 1.0,
        unit: str | None = None,
    ) -> Self:
        return cls(
            value=value,
            provenance=Provenance(
                source_key=source_key,
                source_class=SourceClass.CALCULATED,
                retrieved_at=datetime.now(UTC),
                confidence=confidence,
            ),
            unit=unit,
        )

    def to_envelope(self) -> dict[str, Any]:
        """The API envelope from API.md — provenance ships with every derived value."""
        envelope: dict[str, Any] = {
            "value": self.value,
            "source_class": str(self.provenance.source_class),
            "confidence": round(self.provenance.confidence, 3),
        }
        if self.unit:
            envelope["unit"] = self.unit
        if self.provenance.effective_at:
            envelope["as_of"] = self.provenance.effective_at.isoformat()
        if self.provenance.unavailable_reason:
            envelope["reason"] = self.provenance.unavailable_reason
        if self.provenance.source_url:
            envelope["source_url"] = self.provenance.source_url
        return envelope
