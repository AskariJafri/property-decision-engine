"""The adjustment grid — what a realtor hands you, as a type.

A similarity score says *how much to trust* a comparable. It does not say what
that comparable implies about the subject. Those are different questions, and
the valuation engine previously only answered the first: a 1,300 sq ft sale and
a 1,600 sq ft sale sat in the same weighted average, each pulling the centre
toward its own size rather than toward the subject's.

The sales comparison approach answers the second question by *adjusting* each
sale toward the subject before averaging — add for what the comparable lacked,
subtract for what it had in surplus — so that every adjusted price is an estimate
of the same property. The grid of those adjustments is the working, and it is the
artifact a buyer can put in front of a seller.

Two rules are encoded here rather than left to the implementer:

* **An adjustment carries the rate it used and where that rate came from.** A
  grid whose numbers cannot be traced is a worse artifact than no grid, because
  it looks authoritative.
* **An attribute we could not price is named, not silently skipped.** The absence
  of a time adjustment changes what the range means, and a reader who is not told
  will assume it was applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.money import Cents
from app.engines.valuation.contracts import ScoredComparable


@dataclass(frozen=True, slots=True)
class Adjustment:
    """One line of the grid: what differed, what it was worth, and why that rate."""

    attribute: str
    """Plain language, as it appears in the grid's left column: "living area"."""

    subject_value: str
    comparable_value: str

    amount_cents: Cents
    """Signed, and the sign convention is the one appraisals use: **positive means
    the comparable was inferior**, so its price is adjusted *up* to stand in for the
    subject. A comparable 150 sq ft smaller than the subject gets a positive
    adjustment. This is the opposite of the intuitive "difference from subject",
    and getting it backwards silently inverts the whole valuation."""

    basis: str
    """How the rate was derived, in a sentence a person can check."""


@dataclass(frozen=True, slots=True)
class UnadjustedAttribute:
    """Something that differed and that we refused to price.

    Carries the reason, because "we did not adjust for the extra bedroom" and "the
    extra bedroom is worth nothing" are opposite claims and the grid must not let a
    reader confuse them.
    """

    attribute: str
    reason: str


@dataclass(frozen=True, slots=True)
class AdjustedComparable:
    """A comparable restated as an estimate of the subject."""

    scored: ScoredComparable
    adjustments: tuple[Adjustment, ...]
    unadjusted: tuple[UnadjustedAttribute, ...]

    adjusted_price_cents: Cents
    """The sale price plus every adjustment. What the valuation actually averages."""

    net_adjustment_cents: Cents
    gross_adjustment_cents: Cents
    """Sum of the *absolute* adjustments. The quality signal a net figure hides: a
    comparable adjusted +$80k for size and -$75k for age has a small net and a large
    gross, and the large gross is the honest description of how far it sits from the
    subject. Appraisal practice treats a high gross as grounds to distrust a
    comparable even when its net lands conveniently close."""

    @property
    def gross_adjustment_ratio(self) -> Decimal:
        """Gross adjustment as a share of the original sale price."""
        price = self.scored.comparable.sale_price_cents
        if not price:
            return Decimal(0)
        return (Decimal(self.gross_adjustment_cents) / Decimal(price)).quantize(Decimal("0.0001"))


@dataclass(frozen=True, slots=True)
class AdjustmentGrid:
    """Every adjusted comparable, plus the rate the grid was built on."""

    rows: tuple[AdjustedComparable, ...]

    price_per_square_foot_cents: Cents | None
    """The market rate the size adjustments used, derived from the comparables
    themselves. ``None`` when too few of them stated a floor area to derive one, in
    which case no size adjustment was applied to any row."""

    over_adjusted: tuple[str, ...] = ()
    """Addresses whose gross adjustment exceeded the tolerance. Kept in the grid and
    named, so the user decides whether to drop them; a silent filter would be the
    same mistake the similarity engine already refuses to make."""
