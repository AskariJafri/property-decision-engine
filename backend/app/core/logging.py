"""Structured logging with redaction that cannot be forgotten.

``COMPLIANCE.md`` §4 says income, debts, balances and account identifiers are
never logged. Saying it is not enough — the failure mode is one developer, on one
tired afternoon, logging a whole profile object while debugging, and nobody
noticing for a year.

So redaction is a filter on the logging pipeline rather than a rule in a style
guide. Any log record whose message or extras mention a sensitive key has the
value replaced before a handler ever sees it. The filter is attached in
:func:`configure_logging`, and ``tests/unit/test_logging.py`` proves a financial
value cannot reach a handler even when a caller tries to log one.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

SENSITIVE_KEYS = frozenset(
    {
        "gross_annual_income_cents",
        "household_income_cents",
        "monthly_debt_payments_cents",
        "down_payment_cents",
        "available_savings_cents",
        "emergency_fund_cents",
        "fhsa_balance_cents",
        "rrsp_hbp_available_cents",
        "desired_max_monthly_cents",
        "income",
        "debts",
        "balance",
        "account_number",
        "password",
        "session_secret",
        "credit_score",
    }
)

REDACTED = "[redacted]"

_KEY_VALUE = re.compile(
    r"(?P<key>" + "|".join(sorted(SENSITIVE_KEYS, key=len, reverse=True)) + r")"
    r"(?P<sep>['\"]?\s*[:=]\s*['\"]?)(?P<value>-?[\w.@$,]+)",
    re.IGNORECASE,
)


def redact(value: Any) -> Any:
    """Recursively replace sensitive values in mappings, sequences and strings."""
    if isinstance(value, dict):
        return {
            key: (REDACTED if str(key).lower() in SENSITIVE_KEYS else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(redact(item) for item in value)
    if isinstance(value, str):
        return _KEY_VALUE.sub(lambda m: f"{m.group('key')}{m.group('sep')}{REDACTED}", value)
    return value


class RedactionFilter(logging.Filter):
    """Scrubs every record before a handler formats it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.msg)
        if record.args:
            record.args = (
                redact(record.args)
                if isinstance(record.args, dict)
                else tuple(redact(arg) for arg in record.args)
            )
        for key, value in list(record.__dict__.items()):
            if key in SENSITIVE_KEYS:
                record.__dict__[key] = REDACTED
            elif isinstance(value, (dict, list, tuple)):
                record.__dict__[key] = redact(value)
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line: identifiers and events, never values."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if (
                key.startswith("_")
                or key in logging.LogRecord("", 0, "", 0, "", None, None).__dict__
            ):
                continue
            if key not in {"message", "asctime"}:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.addFilter(RedactionFilter())
    root.setLevel(level)
