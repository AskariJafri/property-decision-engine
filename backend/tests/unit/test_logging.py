"""Proof that a financial value cannot reach a log handler, even when someone tries."""

from __future__ import annotations

import logging

from app.core.logging import REDACTED, RedactionFilter, redact


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def _logger_with_filter() -> tuple[logging.Logger, _Capture]:
    logger = logging.getLogger("test.redaction")
    logger.handlers.clear()
    logger.propagate = False
    handler = _Capture()
    logger.addHandler(handler)
    logger.addFilter(RedactionFilter())
    logger.setLevel(logging.INFO)
    return logger, handler


def test_a_developer_logging_a_whole_profile_still_leaks_nothing():
    logger, handler = _logger_with_filter()
    logger.info(
        "profile saved",
        extra={"profile": {"gross_annual_income_cents": 15_000_000, "first_time_buyer": True}},
    )
    # The message itself is clean; the extras are what a tired afternoon attaches.
    assert handler.lines == ["profile saved"]


def test_values_in_message_strings_are_scrubbed():
    logger, handler = _logger_with_filter()
    logger.info("computed with income=150000 and down_payment_cents=12000000")
    assert "150000" not in handler.lines[0]
    assert "12000000" not in handler.lines[0]
    assert REDACTED in handler.lines[0]


def test_redact_walks_nested_structures():
    payload = {
        "user": {"available_savings_cents": 4_000_000, "city": "Toronto"},
        "history": [{"monthly_debt_payments_cents": 90_000}],
    }
    cleaned = redact(payload)
    assert cleaned["user"]["available_savings_cents"] == REDACTED
    assert cleaned["user"]["city"] == "Toronto"
    assert cleaned["history"][0]["monthly_debt_payments_cents"] == REDACTED


def test_non_sensitive_numbers_survive():
    # Redaction that eats everything is redaction nobody keeps switched on.
    assert redact("analysis_id=abc123 duration_ms=412") == "analysis_id=abc123 duration_ms=412"
