"""Side-by-side comparison of analysed properties: how they differ, and the trade-offs.

It never picks a winner. A buyer weighs a lower monthly cost against more cash up
front, or a shorter commute against a smaller yard, by their own priorities — so
the output states differences as facts and trade-offs as pairs, and leaves the
weighing to the person whose money it is.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ComparisonInput:
    label: str
    purchase_price_cents: int
    down_payment_cents: int
    mortgage_principal_cents: int
    monthly_payment_cents: int
    monthly_property_tax_cents: int
    monthly_condo_fee_cents: int
    monthly_insurance_cents: int
    monthly_maintenance_cents: int
    monthly_carrying_cost_cents: int
    closing_costs_cents: int
    cash_required_cents: int
    five_year_outlay_cents: int
    ten_year_outlay_cents: int
    ten_year_equity_no_growth_cents: int
    ten_year_equity_mid_growth_cents: int
    risk_count: int
    missing_count: int
    high_priority_missing: int


@dataclass(frozen=True, slots=True)
class Difference:
    metric: str
    label: str
    lowest_label: str
    highest_label: str
    spread_cents: int
    sentence: str


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    differences: tuple[Difference, ...]
    trade_offs: tuple[str, ...]
    notes: tuple[str, ...]


METRICS: tuple[tuple[str, str], ...] = (
    ("purchase_price_cents", "Purchase price"),
    ("monthly_carrying_cost_cents", "Monthly carrying cost"),
    ("cash_required_cents", "Cash required upfront"),
    ("closing_costs_cents", "Closing costs"),
    ("monthly_condo_fee_cents", "Condo fee"),
    ("monthly_property_tax_cents", "Property tax (monthly)"),
    ("ten_year_outlay_cents", "10-year total outlay"),
    ("ten_year_equity_no_growth_cents", "10-year equity with no appreciation"),
)


def _dollars(amount_cents: int) -> str:
    return f"${abs(amount_cents) // 100:,}"


def compare(items: list[ComparisonInput]) -> ComparisonResult:
    if not 2 <= len(items) <= 5:
        raise ValueError("compare between two and five properties")

    differences: list[Difference] = []
    for metric, label in METRICS:
        values = [(getattr(item, metric), item.label) for item in items]
        low = min(values)
        high = max(values)
        spread = high[0] - low[0]
        if spread == 0:
            continue
        differences.append(
            Difference(
                metric=metric,
                label=label,
                lowest_label=low[1],
                highest_label=high[1],
                spread_cents=spread,
                sentence=f"{label} ranges from {_dollars(low[0])} ({low[1]}) to "
                f"{_dollars(high[0])} ({high[1]}), a difference of {_dollars(spread)}.",
            )
        )

    trade_offs: list[str] = []
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            monthly = a.monthly_carrying_cost_cents - b.monthly_carrying_cost_cents
            upfront = a.cash_required_cents - b.cash_required_cents
            if monthly and upfront and (monthly > 0) != (upfront > 0):
                cheaper_monthly, dearer_monthly = (b, a) if monthly > 0 else (a, b)
                trade_offs.append(
                    f"{cheaper_monthly.label} costs {_dollars(monthly)} a month less to carry "
                    f"than {dearer_monthly.label}, but needs {_dollars(upfront)} more cash "
                    "upfront."
                )
            equity = a.ten_year_equity_no_growth_cents - b.ten_year_equity_no_growth_cents
            outlay = a.ten_year_outlay_cents - b.ten_year_outlay_cents
            if equity and outlay and (equity > 0) == (outlay > 0):
                more, less = (a, b) if equity > 0 else (b, a)
                trade_offs.append(
                    f"Over ten years {more.label} builds about {_dollars(equity)} more equity "
                    f"than {less.label} (with no appreciation), and costs about "
                    f"{_dollars(outlay)} more in total to own."
                )
            gap = a.high_priority_missing - b.high_priority_missing
            if gap:
                unknown, known = (a, b) if gap > 0 else (b, a)
                trade_offs.append(
                    f"{unknown.label} has {abs(gap)} more high-priority unknown"
                    f"{'s' if abs(gap) != 1 else ''} to investigate than {known.label}, so its "
                    "figures are less certain."
                )

    notes = (
        "These properties are compared on the same assumptions. Differences in assumed "
        "costs (insurance, utilities, maintenance) come from each property's type and "
        "price, not from anything known about the specific home.",
        "No property is ranked as best. Which trade-off matters more depends on your priorities.",
    )
    return ComparisonResult(
        differences=tuple(differences), trade_offs=tuple(trade_offs), notes=notes
    )
