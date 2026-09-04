from decimal import Decimal

import pytest

from app.core.money import allocate, apply_rate, cents, format_cad, from_dollars, to_dollars


def test_from_dollars_rejects_float():
    # The whole point of the module: 0.1 is not 0.1, and a mortgage adds it 360 times.
    with pytest.raises(TypeError):
        from_dollars(850000.55)  # type: ignore[arg-type]


def test_from_dollars_rounds_half_up():
    assert from_dollars("0.005") == 1
    assert from_dollars("850000.554") == 85000055
    assert from_dollars(Decimal("1234.567")) == 123457


def test_round_trip_is_exact():
    amount = from_dollars("850000.00")
    assert to_dollars(amount) == Decimal("850000.00")
    assert format_cad(amount) == "$850,000.00"
    assert format_cad(amount, decimals=False) == "$850,000"


def test_apply_rate_rounds_to_the_cent():
    # Ontario LTT's top marginal band, applied to a round number.
    assert apply_rate(cents(100_000_00), Decimal("0.025")) == 250_000


def test_allocate_never_loses_or_invents_a_cent():
    parts = allocate(cents(10_000), 3)
    assert parts == [3334, 3333, 3333]
    assert sum(parts) == 10_000


def test_allocate_rejects_zero_parts():
    with pytest.raises(ValueError):
        allocate(cents(100), 0)


def test_cents_rejects_bool():
    # bool is an int in Python, and True dollars is not a number anyone meant.
    with pytest.raises(TypeError):
        cents(True)  # type: ignore[arg-type]
