"""The adjustment grid: the sign convention, the derived rate, and what it refuses.

Most of these pin down refusals rather than calculations. That is deliberate — the
engine's whole design bet is that a grid which declines to price what it cannot
source is worth more than one that fills every cell, and a refusal nobody asserts
is a refusal that quietly becomes a constant in six months.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.money import cents
from app.engines.comparables.engine import (
    GROSS_ADJUSTMENT_TOLERANCE,
    MARGINAL_AREA_RATE,
    build_grid,
    derive_price_per_square_foot,
)
from app.engines.valuation.contracts import Comparable, ScoredComparable
from app.engines.valuation.engine import compute_fair_value

AS_OF = date(2026, 9, 1)


def comp(
    address: str,
    price_dollars: int,
    *,
    square_feet: int | None = None,
    bedrooms: int | None = None,
    sold: date = date(2026, 9, 1),
    included: bool = True,
    similarity: str = "0.90",
) -> ScoredComparable:
    return ScoredComparable(
        comparable=Comparable(
            address=address,
            sale_price_cents=cents(price_dollars * 100),
            sale_date=sold,
            square_feet=square_feet,
            bedrooms=bedrooms,
        ),
        similarity=Decimal(similarity),
        distance_m=None,
        included=included,
        reason="fixture",
        weight=Decimal(similarity) if included else Decimal(0),
    )


class TestTheRate:
    def test_the_rate_is_derived_from_the_comparables_not_assumed(self):
        rate = derive_price_per_square_foot(
            (
                comp("A", 800_000, square_feet=1_000),
                comp("B", 900_000, square_feet=1_000),
            )
        )
        assert rate == cents(85_000)  # median of $800/sq ft and $900/sq ft

    def test_a_mistyped_square_footage_does_not_move_the_rate(self):
        """The reason it is a median. 1,450 entered as 145 is a ten-fold error in
        one cell, and a mean would carry it straight into every adjustment."""
        clean = derive_price_per_square_foot(
            (
                comp("A", 800_000, square_feet=1_000),
                comp("B", 810_000, square_feet=1_000),
                comp("C", 820_000, square_feet=1_000),
            )
        )
        with_typo = derive_price_per_square_foot(
            (
                comp("A", 800_000, square_feet=1_000),
                comp("B", 810_000, square_feet=1_000),
                comp("C", 820_000, square_feet=100),
            )
        )
        assert clean == with_typo

    def test_one_comparable_is_not_enough_to_derive_a_rate(self):
        assert derive_price_per_square_foot((comp("A", 800_000, square_feet=1_000),)) is None

    def test_excluded_comparables_do_not_set_the_rate(self):
        rate = derive_price_per_square_foot(
            (
                comp("A", 800_000, square_feet=1_000),
                comp("B", 810_000, square_feet=1_000),
                comp("C", 2_000_000, square_feet=1_000, included=False),
            )
        )
        assert rate == cents(80_500)


class TestTheSignConvention:
    def test_a_smaller_comparable_is_adjusted_upward(self):
        """The convention that inverts the whole valuation if it is backwards: a
        positive adjustment means the comparable was *inferior* and its price has to
        rise to stand in for the subject."""
        grid = build_grid(
            comparables=(
                comp("A", 800_000, square_feet=1_000),
                comp("B", 820_000, square_feet=1_000),
            ),
            subject_square_feet=1_200,
            subject_bedrooms=None,
            as_of=AS_OF,
        ).value

        row = grid.rows[0]
        assert row.net_adjustment_cents > 0
        assert row.adjusted_price_cents > row.scored.comparable.sale_price_cents

    def test_a_larger_comparable_is_adjusted_downward(self):
        grid = build_grid(
            comparables=(
                comp("A", 800_000, square_feet=1_000),
                comp("B", 820_000, square_feet=1_000),
            ),
            subject_square_feet=800,
            subject_bedrooms=None,
            as_of=AS_OF,
        ).value

        assert grid.rows[0].net_adjustment_cents < 0

    def test_the_size_adjustment_is_damped_to_the_marginal_rate(self):
        grid = build_grid(
            comparables=(
                comp("A", 1_000_000, square_feet=1_000),
                comp("B", 1_000_000, square_feet=1_000),
            ),
            subject_square_feet=1_100,
            subject_bedrooms=None,
            as_of=AS_OF,
        ).value

        # $1,000/sq ft derived, 100 sq ft short, damped by the marginal rate.
        expected = int(100 * 100_000 * MARGINAL_AREA_RATE)
        assert grid.rows[0].net_adjustment_cents == expected


class TestWhatItRefusesToPrice:
    def test_an_unmoved_sale_date_is_named_rather_than_skipped(self):
        """No index is wired into this deployment, and a reader who is not told
        will assume the price was brought forward to today."""
        grid = build_grid(
            comparables=(
                comp("A", 800_000, square_feet=1_000, sold=date(2025, 3, 1)),
                comp("B", 820_000, square_feet=1_000, sold=date(2025, 3, 1)),
            ),
            subject_square_feet=1_000,
            subject_bedrooms=None,
            as_of=AS_OF,
        ).value

        reasons = [u.attribute for u in grid.rows[0].unadjusted]
        assert "sale date" in reasons
        assert not any(a.attribute == "sale date" for a in grid.rows[0].adjustments)

    def test_a_sale_date_is_priced_once_a_trend_is_supplied(self):
        grid = build_grid(
            comparables=(
                comp("A", 1_000_000, square_feet=1_000, sold=date(2026, 6, 1)),
                comp("B", 1_000_000, square_feet=1_000, sold=date(2026, 6, 1)),
            ),
            subject_square_feet=1_000,
            subject_bedrooms=None,
            as_of=AS_OF,
            market_trend_monthly=Decimal("0.01"),
        ).value

        line = next(a for a in grid.rows[0].adjustments if a.attribute == "sale date")
        assert line.amount_cents == 3_000_000  # 3 months at 1% of $1,000,000

    def test_a_bedroom_difference_is_named_and_never_priced(self):
        grid = build_grid(
            comparables=(
                comp("A", 800_000, square_feet=1_000, bedrooms=2),
                comp("B", 820_000, square_feet=1_000, bedrooms=2),
            ),
            subject_square_feet=1_000,
            subject_bedrooms=4,
            as_of=AS_OF,
        ).value

        assert any(u.attribute == "bedrooms" for u in grid.rows[0].unadjusted)
        assert not any(a.attribute == "bedrooms" for a in grid.rows[0].adjustments)

    def test_without_a_derivable_rate_size_is_named_not_guessed(self):
        grid = build_grid(
            comparables=(comp("A", 800_000, square_feet=1_000),),
            subject_square_feet=1_400,
            subject_bedrooms=None,
            as_of=AS_OF,
        ).value

        assert grid.price_per_square_foot_cents is None
        assert grid.rows[0].adjustments == ()
        assert any(u.attribute == "living area" for u in grid.rows[0].unadjusted)


class TestQualitySignals:
    def test_gross_adjustment_exceeds_net_when_adjustments_oppose(self):
        """The signal a net figure hides. Up for size, down for time, small net and
        a large gross — and the gross is the honest description."""
        grid = build_grid(
            comparables=(
                comp("A", 1_000_000, square_feet=800, sold=date(2026, 6, 1)),
                comp("B", 1_000_000, square_feet=800, sold=date(2026, 6, 1)),
            ),
            subject_square_feet=1_000,
            subject_bedrooms=None,
            as_of=AS_OF,
            market_trend_monthly=Decimal("-0.01"),
        ).value

        row = grid.rows[0]
        assert row.gross_adjustment_cents > abs(row.net_adjustment_cents)

    def test_an_over_adjusted_comparable_is_flagged_and_kept(self):
        """Named rather than dropped. A silent filter is the mistake the similarity
        engine already refuses to make, and this is the same mistake."""
        grid = build_grid(
            comparables=(
                comp("Tiny", 500_000, square_feet=500),
                comp("B", 1_000_000, square_feet=1_000),
            ),
            subject_square_feet=1_500,
            subject_bedrooms=None,
            as_of=AS_OF,
        ).value

        assert "Tiny" in grid.over_adjusted
        assert any(r.scored.comparable.address == "Tiny" for r in grid.rows)
        assert grid.rows[0].gross_adjustment_ratio > GROSS_ADJUSTMENT_TOLERANCE


class TestFairValueUsesTheGrid:
    def test_adjusted_prices_move_the_centre_toward_the_subject(self):
        """Two sales of 1,000 sq ft homes say little directly about a 1,400 sq ft
        subject. Unadjusted they drag the centre to their own size; adjusted, they
        estimate the subject."""
        comparables = (
            comp("A", 800_000, square_feet=1_000),
            comp("B", 820_000, square_feet=1_000),
        )
        grid = build_grid(
            comparables=comparables,
            subject_square_feet=1_400,
            subject_bedrooms=None,
            as_of=AS_OF,
        ).value

        without = compute_fair_value(
            asking_price_cents=cents(100_000_000),
            comparables=comparables,
            subject_square_feet=1_400,
        ).value
        with_grid = compute_fair_value(
            asking_price_cents=cents(100_000_000),
            comparables=comparables,
            subject_square_feet=1_400,
            adjusted=grid.rows,
        ).value

        assert with_grid.low_cents != without.low_cents

    def test_the_grid_is_ignored_when_it_does_not_cover_every_included_sale(self):
        """A partial grid would average adjusted and unadjusted prices together,
        which is the one arrangement guaranteed to be wrong."""
        comparables = (
            comp("A", 800_000, square_feet=1_000),
            comp("B", 820_000, square_feet=1_000),
        )
        full = compute_fair_value(
            asking_price_cents=cents(100_000_000),
            comparables=comparables,
            subject_square_feet=1_000,
        ).value
        partial_grid = build_grid(
            comparables=comparables[:1],
            subject_square_feet=1_000,
            subject_bedrooms=None,
            as_of=AS_OF,
        ).value
        partial = compute_fair_value(
            asking_price_cents=cents(100_000_000),
            comparables=comparables,
            subject_square_feet=1_000,
            adjusted=partial_grid.rows,
        ).value

        assert partial.low_cents == full.low_cents
