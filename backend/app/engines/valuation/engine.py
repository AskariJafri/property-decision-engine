"""Fair value and comparable similarity — v1, over comparables the user supplied.

The spread is driven by evidence, not by confidence in a model
(``SCORING_MODEL.md`` §4): with no comparables the range is ±12% and confidence is
capped at 0.45; with six well-matched ones it narrows to ±4%. That turns the one
genuinely gated dataset in this product into a dial the user can turn by spending
five minutes pasting what their realtor already sent them.

Similarity is an explicit weighted distance with reasons attached, because "we
ignored the cheap one across the tracks, and here is why" builds more trust than a
silent filter.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.money import Cents, apply_rate, cents
from app.engines.base import EngineResult, TraceBuilder
from app.engines.valuation.contracts import (
    Comparable,
    FairValueRange,
    ScoredComparable,
    ValuationBasis,
)

MIN_SIMILARITY = Decimal("0.70")

#: spread, confidence cap — indexed by how much comparable evidence exists.
EVIDENCE_TIERS: tuple[tuple[int, Decimal, Decimal, Decimal], ...] = (
    (6, Decimal("0.85"), Decimal("0.04"), Decimal("0.85")),
    (3, Decimal("0.80"), Decimal("0.06"), Decimal("0.75")),
    (1, Decimal("0"), Decimal("0.09"), Decimal("0.60")),
)
NO_EVIDENCE_SPREAD = Decimal("0.12")
NO_EVIDENCE_CONFIDENCE = Decimal("0.45")


def score_comparable(
    *,
    subject_square_feet: int | None,
    subject_bedrooms: int | None,
    comparable: Comparable,
    distance_m: int | None,
    as_of: date,
) -> ScoredComparable:
    """A weighted similarity, with the reason it was kept or dropped."""
    parts: list[tuple[Decimal, Decimal]] = []
    notes: list[str] = []

    if distance_m is not None:
        # Decay to zero at 5km; a sale five kilometres away is a different market.
        closeness = max(Decimal(0), Decimal(1) - Decimal(distance_m) / Decimal(5000))
        parts.append((closeness, Decimal("0.20")))
        notes.append(f"{distance_m} m away")

    months = max(
        0, (as_of.year - comparable.sale_date.year) * 12 + as_of.month - comparable.sale_date.month
    )
    recency = max(Decimal(0), Decimal(1) - Decimal(months) / Decimal(18))
    parts.append((recency, Decimal("0.20")))
    notes.append(f"sold {months} months ago" if months else "sold this month")

    if subject_square_feet and comparable.square_feet:
        difference = abs(comparable.square_feet - subject_square_feet) / subject_square_feet
        parts.append((max(Decimal(0), Decimal(1) - Decimal(str(difference)) * 2), Decimal("0.15")))
        notes.append(f"{comparable.square_feet:,} sq ft")

    if subject_bedrooms is not None and comparable.bedrooms is not None:
        gap = abs(comparable.bedrooms - subject_bedrooms)
        parts.append((max(Decimal(0), Decimal(1) - Decimal(gap) / Decimal(3)), Decimal("0.10")))
        notes.append(f"{comparable.bedrooms} bed")

    if not parts:
        similarity = Decimal("0.5")
    else:
        weight_total = sum(w for _, w in parts)
        similarity = (sum((s * w for s, w in parts), start=Decimal(0)) / weight_total).quantize(
            Decimal("0.001")
        )

    included = similarity >= MIN_SIMILARITY
    reason = (
        f"Included at {similarity:.0%} similarity — {', '.join(notes)}."
        if included
        else f"Excluded at {similarity:.0%} similarity, below the {MIN_SIMILARITY:.0%} floor — "
        f"{', '.join(notes)}."
    )
    return ScoredComparable(
        comparable=comparable,
        similarity=similarity,
        distance_m=distance_m,
        included=included,
        reason=reason,
        weight=similarity if included else Decimal(0),
    )


def compute_fair_value(
    *,
    asking_price_cents: Cents,
    comparables: tuple[ScoredComparable, ...],
    subject_square_feet: int | None = None,
) -> EngineResult[FairValueRange]:
    """A range, never a point. "Fair value $832,451" is a lie about precision."""
    trace = TraceBuilder()
    included = [c for c in comparables if c.included]

    if not included:
        # Nothing to anchor on but the asking price itself, so the range is wide and
        # the note says exactly why.
        spread = NO_EVIDENCE_SPREAD
        confidence = NO_EVIDENCE_CONFIDENCE
        centre = asking_price_cents
        basis = ValuationBasis.MARKET_BENCHMARK_ONLY
        note = (
            "No comparable sales supplied, so this range is anchored on the asking price "
            "alone. Add three or four recent sales nearby and it narrows sharply."
        )
        trace.assume(
            "valuation_anchor",
            "asking price",
            "With no comparables, the asking price is the only anchor available. That "
            "makes this a sanity band, not an independent valuation.",
        )
    else:
        weight_total = sum((c.weight for c in included), start=Decimal(0))
        if subject_square_feet and all(c.comparable.square_feet for c in included):
            # Price per square foot, weighted by similarity, applied to the subject.
            psf = (
                sum(
                    (
                        Decimal(c.comparable.sale_price_cents)
                        / Decimal(c.comparable.square_feet or 1)
                        * c.weight
                        for c in included
                    ),
                    start=Decimal(0),
                )
                / weight_total
            )
            centre = cents(int(psf * Decimal(subject_square_feet)))
            method = "similarity-weighted price per square foot"
        else:
            centre = cents(
                int(
                    sum(
                        (Decimal(c.comparable.sale_price_cents) * c.weight for c in included),
                        start=Decimal(0),
                    )
                    / weight_total
                )
            )
            method = "similarity-weighted mean sale price"

        mean_similarity = weight_total / Decimal(len(included))
        spread, confidence = NO_EVIDENCE_SPREAD, NO_EVIDENCE_CONFIDENCE
        for count, similarity_floor, tier_spread, tier_confidence in EVIDENCE_TIERS:
            if len(included) >= count and mean_similarity >= similarity_floor:
                spread, confidence = tier_spread, tier_confidence
                break
        basis = ValuationBasis.USER_COMPARABLES
        note = (
            f"Based on {len(included)} comparable sale{'s' if len(included) != 1 else ''} you "
            f"supplied, at {mean_similarity:.0%} average similarity, using a {method}."
        )
        trace.step(
            "comparable centre",
            method,
            {"comparables": len(included), "mean_similarity": str(mean_similarity)},
            centre,
            unit="cents",
        )

    low = trace.step(
        "fair value low",
        "centre * (1 - spread)",
        {"centre_cents": centre, "spread": str(spread)},
        cents(centre - apply_rate(centre, spread)),
        unit="cents",
    )
    high = trace.step(
        "fair value high",
        "centre * (1 + spread)",
        {"centre_cents": centre, "spread": str(spread)},
        cents(centre + apply_rate(centre, spread)),
        unit="cents",
    )

    return trace.finish(
        FairValueRange(
            low_cents=low,
            high_cents=high,
            basis=basis,
            confidence=confidence,
            note=note,
        ),
        confidence=float(confidence),
    )


def suggested_offer(
    *, fair_value: FairValueRange, asking_price_cents: Cents
) -> tuple[Cents, Cents]:
    """An analytical range, deliberately narrower than fair value and never above ask.

    Presented as analysis, not as advice on what to offer — the language distinction
    ``COMPLIANCE.md`` §2 flags for review.
    """
    low = min(fair_value.low_cents, asking_price_cents)
    high = min(fair_value.high_cents, asking_price_cents)
    if high < low:
        high = low
    return cents(low), cents(high)
