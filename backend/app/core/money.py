"""Money is an integer number of cents, and nothing else.

A float cannot represent $0.10, and a mortgage is a loop that adds a number to
itself three hundred and sixty times. The error is not theoretical: amortize a
float balance over 25 years and the final payment is wrong by enough to be
visible in a UI that promises reproducibility.

So every monetary quantity in this system is ``Cents`` — a plain ``int`` — from
the database column through the engine to the JSON field, whose name ends in
``_cents`` so that a reader never has to guess the unit.

The only place a decimal appears is at the presentation boundary, and it appears
through :func:`format_cad`, which does the rounding once, explicitly, where a
human can see it.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import NewType

Cents = NewType("Cents", int)

ZERO = Cents(0)


def cents(value: int) -> Cents:
    """Build a Cents from a whole number of cents."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"cents() takes an int, got {type(value).__name__}")
    return Cents(value)


def from_dollars(amount: str | int | Decimal) -> Cents:
    """Parse a dollar amount into cents.

    Takes a string or Decimal rather than a float on purpose — ``from_dollars(0.1)``
    would be a quiet invitation to the exact problem this module exists to avoid.
    Half-up rounding matches how a person reading a price expects it to round, and
    matches the convention Canadian lenders use on payment schedules.
    """
    # The annotation excludes float; this guard is for the untyped callers that a
    # type checker never sees — JSON bodies, form fields, a REPL at 2am.
    if isinstance(amount, float):
        raise TypeError("from_dollars() refuses float; pass a str or Decimal")
    quantized = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Cents(int(quantized * 100))


def to_dollars(amount: Cents) -> Decimal:
    """Exact dollar value, for display and for report generation."""
    return Decimal(amount) / Decimal(100)


def format_cad(amount: Cents, *, decimals: bool = True) -> str:
    """Render cents as Canadian dollars. The presentation boundary, and the only one."""
    dollars = to_dollars(amount)
    return f"${dollars:,.2f}" if decimals else f"${dollars:,.0f}"


def apply_rate(amount: Cents, rate: Decimal) -> Cents:
    """Multiply money by a rate, rounding half-up to the cent.

    Used by every bracket, premium and percentage calculation, so that rounding
    happens in exactly one place and a test can pin it.
    """
    product = (Decimal(amount) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return Cents(int(product))


def allocate(amount: Cents, parts: int) -> list[Cents]:
    """Split money into parts that sum back to the original, exactly.

    Naive division loses or invents cents; splitting $100.00 three ways as
    33.33 × 3 leaves a cent unaccounted for. The remainder is distributed one
    cent at a time to the earliest parts, which is the convention a bookkeeper
    expects and, more usefully, one that always reconciles.
    """
    if parts <= 0:
        raise ValueError("parts must be positive")
    base, remainder = divmod(amount, parts)
    return [Cents(base + (1 if i < remainder else 0)) for i in range(parts)]
