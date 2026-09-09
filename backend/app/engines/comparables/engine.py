"""The sales comparison approach, over comparables the user supplied.

The rate problem is the whole problem. An adjustment grid is only as defensible
as the dollar figures in it, and the honest ways to get those figures — paired
sales analysis, or a regression over a few hundred transactions — both need the
dataset this product does not have. Inventing plausible constants would produce a
grid that looks exactly like a defensible one and is not, which is worse than
producing nothing.

So this engine prices exactly what the evidence in front of it can price:

* **Living area**, from the price per square foot implied by the user's own
  comparables. The rate is derived, not assumed, and it is stated in the output.
* **Sale date**, only when a market trend is supplied. No index is wired into this
  deployment, so by default the time adjustment is *not applied* and says so.

Everything else that differs — bedrooms, age, lot, kind — is named as unadjusted
with the reason. Those attributes are not ignored: they already move the
similarity weight in ``engines.valuation``, which is the defensible way to use a
difference you cannot price. Weighting by similarity says "trust this one less".
Adjusting says "this one implies that figure". The second is a stronger claim and
needs a rate to back it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from statistics import median

from app.core.money import Cents, cents, format_cad
from app.engines.base import EngineResult, TraceBuilder
from app.engines.comparables.contracts import (
    AdjustedComparable,
    Adjustment,
    AdjustmentGrid,
    UnadjustedAttribute,
)
from app.engines.valuation.contracts import ScoredComparable

MIN_COMPARABLES_FOR_RATE = 2
"""Below this, a median price per square foot is one sale wearing a statistic's
clothing. With none derivable the grid still renders — every row simply carries a
size line in ``unadjusted`` instead of an adjustment."""

MARGINAL_AREA_RATE = Decimal("0.5")
"""The share of average price per square foot applied to a size *difference*.

Average $/sq ft is not the marginal value of one more square foot: it includes
land, services and the fixed cost of a kitchen and a furnace, none of which scale
with floor area. Adjusting a 150 sq ft gap at the full average therefore
overstates it, and does so in the direction that flatters whichever comparable is
smallest. Half is a damping factor, not a measurement — it is recorded as an
assumption on every grid so it reads as the judgement it is.
"""

GROSS_ADJUSTMENT_TOLERANCE = Decimal("0.15")
"""Gross adjustment above this share of sale price and the comparable is named in
``over_adjusted``. A sale needing 15% of its price moved to stand in for the
subject is describing a different property, however close the net lands."""


def derive_price_per_square_foot(comparables: tuple[ScoredComparable, ...]) -> Cents | None:
    """The market rate, from the included comparables that stated a floor area.

    Median rather than mean, and deliberately: one mispasted square footage — a
    1,450 typed as 145 — moves a mean by an order of magnitude and a median not at
    all. User-entered data is exactly where that happens.
    """
    rates = [
        Decimal(c.comparable.sale_price_cents) / Decimal(c.comparable.square_feet)
        for c in comparables
        if c.included and c.comparable.square_feet
    ]
    if len(rates) < MIN_COMPARABLES_FOR_RATE:
        return None
    return cents(int(median(rates)))


def adjust_comparable(
    *,
    scored: ScoredComparable,
    subject_square_feet: int | None,
    subject_bedrooms: int | None,
    price_per_square_foot_cents: Cents | None,
    as_of: date,
    market_trend_monthly: Decimal | None = None,
) -> AdjustedComparable:
    """Restate one sale as an estimate of the subject.

    ``market_trend_monthly`` is the monthly rate of change in local prices, e.g.
    ``Decimal("0.004")`` for a market rising 0.4% a month. Supplied by a caller that
    has an index; ``None`` — the state of this deployment — means no time adjustment
    and a line saying so.
    """
    comparable = scored.comparable
    adjustments: list[Adjustment] = []
    unadjusted: list[UnadjustedAttribute] = []

    # Living area. Positive when the comparable is smaller than the subject: its
    # price has to come up to stand in for the larger property.
    if subject_square_feet and comparable.square_feet and price_per_square_foot_cents:
        difference = subject_square_feet - comparable.square_feet
        amount = int(
            Decimal(difference) * Decimal(price_per_square_foot_cents) * MARGINAL_AREA_RATE
        )
        if amount:
            adjustments.append(
                Adjustment(
                    attribute="living area",
                    subject_value=f"{subject_square_feet:,} sq ft",
                    comparable_value=f"{comparable.square_feet:,} sq ft",
                    amount_cents=cents(amount),
                    basis=(
                        f"{difference:+,} sq ft at "
                        f"{format_cad(price_per_square_foot_cents)}/sq ft "
                        f"× {MARGINAL_AREA_RATE} marginal rate"
                    ),
                )
            )
    elif subject_square_feet and comparable.square_feet:
        unadjusted.append(
            UnadjustedAttribute(
                attribute="living area",
                reason=(
                    "Too few comparables stated a floor area to derive a price per "
                    "square foot, so the size difference is reflected in the similarity "
                    "weight rather than in dollars."
                ),
            )
        )
    elif subject_square_feet or comparable.square_feet:
        unadjusted.append(
            UnadjustedAttribute(
                attribute="living area",
                reason="One of the two properties did not state a floor area.",
            )
        )

    # Sale date. Only with an index; otherwise the omission is stated.
    months = max(
        0,
        (as_of.year - comparable.sale_date.year) * 12 + as_of.month - comparable.sale_date.month,
    )
    if months and market_trend_monthly is not None:
        amount = int(Decimal(comparable.sale_price_cents) * market_trend_monthly * Decimal(months))
        if amount:
            adjustments.append(
                Adjustment(
                    attribute="sale date",
                    subject_value=as_of.isoformat(),
                    comparable_value=comparable.sale_date.isoformat(),
                    amount_cents=cents(amount),
                    basis=(
                        f"{months} month{'s' if months != 1 else ''} at "
                        f"{market_trend_monthly:+.2%} per month"
                    ),
                )
            )
    elif months:
        unadjusted.append(
            UnadjustedAttribute(
                attribute="sale date",
                reason=(
                    f"Sold {months} month{'s' if months != 1 else ''} ago, and no market "
                    "index is configured for this jurisdiction, so the price has not been "
                    "moved to today. In a market that has shifted since then this range "
                    "is stale in that direction."
                ),
            )
        )

    if (
        subject_bedrooms is not None
        and comparable.bedrooms is not None
        and comparable.bedrooms != subject_bedrooms
    ):
        unadjusted.append(
            UnadjustedAttribute(
                attribute="bedrooms",
                reason=(
                    f"{comparable.bedrooms} against {subject_bedrooms}. Pricing a bedroom "
                    "needs paired sales this product has no licence to obtain, so the "
                    "difference lowers the similarity weight instead of moving the price."
                ),
            )
        )

    net = sum(a.amount_cents for a in adjustments)
    gross = sum(abs(a.amount_cents) for a in adjustments)
    return AdjustedComparable(
        scored=scored,
        adjustments=tuple(adjustments),
        unadjusted=tuple(unadjusted),
        adjusted_price_cents=cents(comparable.sale_price_cents + net),
        net_adjustment_cents=cents(net),
        gross_adjustment_cents=cents(gross),
    )


def build_grid(
    *,
    comparables: tuple[ScoredComparable, ...],
    subject_square_feet: int | None,
    subject_bedrooms: int | None,
    as_of: date,
    market_trend_monthly: Decimal | None = None,
) -> EngineResult[AdjustmentGrid]:
    """The full grid, with the rate it was built on recorded in the trace."""
    trace = TraceBuilder()
    rate = derive_price_per_square_foot(comparables)

    if rate is not None:
        trace.step(
            "price per square foot",
            "median(sale price / square feet) over included comparables",
            {
                "comparables": len(
                    [c for c in comparables if c.included and c.comparable.square_feet]
                ),
            },
            rate,
            unit="cents per square foot",
        )
        trace.assume(
            "marginal_area_rate",
            str(MARGINAL_AREA_RATE),
            "Average price per square foot includes land and the fixed cost of a "
            "dwelling, neither of which scales with floor area, so a size difference "
            "is adjusted at half the average rather than at the full rate.",
        )
    elif any(c.included for c in comparables):
        trace.assume(
            "size_adjustment",
            "not applied",
            f"Fewer than {MIN_COMPARABLES_FOR_RATE} included comparables stated a floor "
            "area, so no price per square foot could be derived from the evidence and "
            "none was assumed.",
        )

    if market_trend_monthly is None:
        trace.assume(
            "market_trend_monthly",
            "unavailable",
            "No market index is wired into this deployment, so sale prices are not "
            "moved forward to today. Older comparables therefore carry whatever the "
            "market has done since, unmeasured.",
        )

    rows = tuple(
        adjust_comparable(
            scored=scored,
            subject_square_feet=subject_square_feet,
            subject_bedrooms=subject_bedrooms,
            price_per_square_foot_cents=rate,
            as_of=as_of,
            market_trend_monthly=market_trend_monthly,
        )
        for scored in comparables
    )

    over = tuple(
        row.scored.comparable.address
        for row in rows
        if row.scored.included and row.gross_adjustment_ratio > GROSS_ADJUSTMENT_TOLERANCE
    )
    for address in over:
        trace.assume(
            "over_adjusted",
            address,
            f"Gross adjustment exceeds {GROSS_ADJUSTMENT_TOLERANCE:.0%} of the sale price. "
            "Still included, and flagged: a sale needing this much movement to stand in "
            "for the subject is describing a different property.",
        )

    return trace.finish(
        AdjustmentGrid(
            rows=rows,
            price_per_square_foot_cents=rate,
            over_adjusted=over,
        ),
        confidence=1.0,
    )
