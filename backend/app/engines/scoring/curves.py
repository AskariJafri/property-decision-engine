"""Piecewise anchors, and the honest statement that they are not yet calibrated.

Every threshold in this module is a defensible prior, not a validated parameter
(``SCORING_MODEL.md`` §9). They are interpolated rather than stepped so that a
dollar of extra income cannot move a score by ten points, and they are kept here,
in one file, so the calibration pass has one place to work.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import pairwise

Anchors = tuple[tuple[Decimal, Decimal], ...]


def piecewise(value: Decimal, anchors: Anchors) -> Decimal:
    """Linear interpolation between anchor points, clamped at both ends.

    Anchors are ``(input, score)`` ordered by input ascending. Below the first
    anchor the first score applies; above the last, the last.
    """
    if not anchors:
        raise ValueError("at least one anchor is required")
    if value <= anchors[0][0]:
        return anchors[0][1]
    if value >= anchors[-1][0]:
        return anchors[-1][1]
    for (x0, y0), (x1, y1) in pairwise(anchors):
        if x0 <= value <= x1:
            if x1 == x0:
                return y1
            span = (value - x0) / (x1 - x0)
            return (y0 + (y1 - y0) * span).quantize(Decimal("0.01"))
    return anchors[-1][1]


def _a(*points: tuple[str, str]) -> Anchors:
    return tuple((Decimal(x), Decimal(y)) for x, y in points)


#: Housing cost as a share of gross income. 0.32 and 0.39 sit near conventional
#: practice and the insured GDS ceiling respectively.
HOUSING_RATIO = _a(("0.25", "100"), ("0.32", "75"), ("0.39", "50"), ("0.45", "25"), ("0.55", "0"))

#: Housing plus other debts. 0.44 is the insured TDS ceiling.
TOTAL_DEBT_RATIO = _a(
    ("0.30", "100"), ("0.38", "75"), ("0.44", "50"), ("0.50", "25"), ("0.60", "0")
)

#: Cost against the budget the household actually stated. Over 1.0 is over budget.
BUDGET_ADHERENCE = _a(("0.85", "100"), ("1.00", "70"), ("1.10", "40"), ("1.25", "0"))

#: Months of ownership cost left in reserve after closing.
RESERVE_MONTHS = _a(("0", "0"), ("1", "35"), ("3", "70"), ("6", "100"))

#: Asking price against the fair-value range, expressed as a position: 0 at the low
#: bound, 1 at the high bound, above 1 over the range.
PRICE_POSITION = _a(
    ("-0.10", "100"), ("0", "92"), ("0.5", "80"), ("1.0", "65"), ("1.10", "35"), ("1.25", "0")
)

#: Commute minutes against the household's stated maximum.
COMMUTE_ADHERENCE = _a(("0.5", "100"), ("0.85", "85"), ("1.0", "65"), ("1.3", "25"), ("2.0", "0"))

#: Walk-style amenity count within a fifteen minute walk.
AMENITY_COUNT = _a(("0", "10"), ("5", "45"), ("15", "75"), ("30", "95"), ("50", "100"))

#: Age of the building in years.
PROPERTY_AGE = _a(("0", "95"), ("10", "90"), ("30", "75"), ("60", "55"), ("100", "40"))

#: Annual cash-on-cash return for an investment purchase.
CASH_ON_CASH = _a(("-0.05", "0"), ("0", "40"), ("0.03", "65"), ("0.06", "85"), ("0.10", "100"))

#: Sales-to-new-listings. Below 0.40 is a buyer's market, above 0.60 a seller's.
BUYER_MARKET = _a(("0.20", "100"), ("0.40", "80"), ("0.60", "50"), ("0.80", "25"), ("1.0", "10"))
