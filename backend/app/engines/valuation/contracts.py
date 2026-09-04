"""Fair value, comparables and risk flags — the contracts for the judgement engines.

Grouped in one module because they form a chain: comparables feed valuation, and
valuation and risk both feed scoring. Phase D and E implement them.

Three rules are encoded in the types rather than left to implementers:

* **A fair value is a range.** There is no ``fair_value_cents`` field anywhere,
  because "$832,451" is a lie about precision even when the midpoint is right.
* **Evidence determines the spread.** :class:`ValuationBasis` and the spread table
  in ``SCORING_MODEL.md`` §4 tie confidence to how many comparables the user
  supplied, which turns the one gated dataset into a dial they can turn.
* **Unknown is not risk.** :class:`RiskStatus` separates ``CONFIRMED`` from
  ``POTENTIAL`` from ``UNKNOWN``, and an ``UNKNOWN`` flag reduces analysis
  confidence while leaving the Risk subscore alone. "We could not check for
  flooding" must never render as "this house floods".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from app.core.money import Cents
from app.engines.base import EngineResult


class ValuationBasis(StrEnum):
    MARKET_BENCHMARK_ONLY = "market_benchmark_only"
    """No comparables supplied. Widest spread, confidence capped at 0.45."""

    USER_COMPARABLES = "user_comparables"
    LICENSED_COMPARABLES = "licensed_comparables"
    """Reserved. Requires a board relationship the free stack does not have."""


@dataclass(frozen=True, slots=True)
class FairValueRange:
    low_cents: Cents
    high_cents: Cents
    basis: ValuationBasis
    confidence: Decimal
    note: str
    """Shown verbatim, e.g. "No comparable sales supplied — add some to narrow this"."""

    def __post_init__(self) -> None:
        if self.high_cents < self.low_cents:
            raise ValueError("fair value high is below low")


@dataclass(frozen=True, slots=True)
class OfferRange:
    low_cents: Cents
    high_cents: Cents
    max_supported_by_profile_cents: Cents | None
    rationale: tuple[str, ...]
    disclaimer: str = (
        "An analytical range from comparables and market conditions. Not advice on what to offer."
    )


@dataclass(frozen=True, slots=True)
class Comparable:
    """A sold property, supplied by the user (ADR 0002 §3).

    ``owner_user_id`` has no place in the engine, but it is ``NOT NULL`` in the
    schema: comps are scoped to the person who supplied them and are never pooled,
    because pooling MLS-derived figures across users recreates the licensing
    problem by another route.
    """

    address: str
    sale_price_cents: Cents
    sale_date: date
    latitude: float | None = None
    longitude: float | None = None
    bedrooms: int | None = None
    bathrooms: Decimal | None = None
    square_feet: int | None = None
    lot_square_feet: int | None = None
    year_built: int | None = None
    property_kind: str | None = None


@dataclass(frozen=True, slots=True)
class ScoredComparable:
    comparable: Comparable
    similarity: Decimal
    distance_m: int | None
    included: bool
    reason: str
    """Plain language, for inclusion or exclusion alike. Silent filters cost trust."""

    weight: Decimal = Decimal("0")


class RiskStatus(StrEnum):
    CONFIRMED = "confirmed"
    POTENTIAL = "potential"
    UNKNOWN = "unknown"


class RiskSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskCategory(StrEnum):
    FLOOD = "flood"
    ZONING = "zoning"
    DEVELOPMENT = "development"
    ENVIRONMENTAL = "environmental"
    CONDITION = "condition"
    TAX = "tax"
    CONDO_FEE = "condo_fee"
    SPECIAL_ASSESSMENT = "special_assessment"
    PRICE_HISTORY = "price_history"
    INSURANCE = "insurance"
    INFRASTRUCTURE = "infrastructure"
    NOISE = "noise"


@dataclass(frozen=True, slots=True)
class RiskFlag:
    category: RiskCategory
    status: RiskStatus
    severity: RiskSeverity
    evidence: str
    explanation: str
    recommended_action: str
    source_key: str
    distance_m: int | None = None
    as_of: date | None = None

    @property
    def affects_score(self) -> bool:
        """UNKNOWN reduces confidence, never the Risk subscore."""
        return self.status is not RiskStatus.UNKNOWN


class ValuationEngine(Protocol):
    def fair_value(
        self,
        *,
        asking_price_cents: Cents,
        comparables: tuple[ScoredComparable, ...],
        benchmark_cents: Cents | None,
    ) -> EngineResult[FairValueRange]: ...


class ComparableEngine(Protocol):
    def score_comparables(
        self,
        *,
        subject_latitude: float | None,
        subject_longitude: float | None,
        subject: Comparable,
        candidates: tuple[Comparable, ...],
        as_of: date,
    ) -> EngineResult[tuple[ScoredComparable, ...]]: ...


class RiskEngine(Protocol):
    def flags(self, *, evidence: dict[str, object]) -> EngineResult[tuple[RiskFlag, ...]]: ...
