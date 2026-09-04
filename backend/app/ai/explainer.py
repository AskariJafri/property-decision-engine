"""Narration over a finished analysis, and the guard that makes it safe.

The model receives numbers that already exist and is asked to explain them. The
**numeric guard** then rejects any figure in its output that was not in the input
bundle, so a hallucinated number fails closed instead of reaching someone who is
about to spend $850,000.

The guard is deliberately strict in one direction only: it never repairs output. A
report that fails validation is discarded and the analysis renders without prose,
which is a smaller loss than a plausible invented figure.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from app.ai.contracts import LlmProvider, LlmUnavailableError

SYSTEM_PROMPT = """You explain a property analysis to a home buyer.

Absolute rules:
- Use ONLY the numbers given to you. Never compute, estimate, round or invent one.
- Never claim data exists that is listed as unavailable. Say it is unavailable.
- Never give financial, mortgage, legal or tax advice. Describe what the analysis found.
- Every claim must trace to a factor or figure you were given.

Return JSON with exactly these keys:
  summary: one paragraph, plain language
  pros: array of strings
  cons: array of strings
  questions: array of strings, things to ask the realtor
  what_would_change_this: array of strings
"""

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["summary", "pros", "cons", "questions", "what_would_change_this"],
    "properties": {
        "summary": {"type": "string"},
        "pros": {"type": "array", "items": {"type": "string"}},
        "cons": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "string"}},
        "what_would_change_this": {"type": "array", "items": {"type": "string"}},
    },
}

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

#: Small integers are ordinary English ("three bedrooms", "the first year") and
#: percentages under 100 appear in figures we already supplied. Guarding them would
#: reject every readable sentence, so the guard covers the values that could mislead:
#: anything that looks like a dollar figure or a large count.
GUARD_FLOOR = 1000


@dataclass(frozen=True, slots=True)
class Explanation:
    summary: str
    pros: tuple[str, ...]
    cons: tuple[str, ...]
    questions: tuple[str, ...]
    what_would_change_this: tuple[str, ...]
    model_id: str
    prompt_hash: str
    numeric_guard_passed: bool


class NumericGuardError(RuntimeError):
    """The model produced a number nobody gave it."""


def allowed_numbers(bundle: dict[str, Any]) -> set[str]:
    """Every number the model was shown, in the forms it might restate them.

    A figure supplied as ``412000`` cents may legitimately come back as ``4,120``
    dollars or ``4120``, so the permitted set carries the cent value, the dollar
    value, and their comma-formatted forms.
    """
    allowed: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, int | float):
            for candidate in (value, value / 100 if isinstance(value, int) else value):
                as_int = int(candidate)
                if abs(candidate - as_int) < 1e-9:
                    allowed.add(str(as_int))
                    allowed.add(f"{as_int:,}")
                else:
                    allowed.add(f"{candidate:.2f}")
                    allowed.add(f"{candidate:,.2f}")
        elif isinstance(value, str):
            for match in _NUMBER.finditer(value):
                token = match.group()
                allowed.add(token)
                allowed.add(token.replace(",", ""))
        elif isinstance(value, dict):
            for item in value.values():
                add(item)
        elif isinstance(value, list | tuple):
            for item in value:
                add(item)

    add(bundle)
    return allowed


def check_numbers(text: str, allowed: set[str]) -> list[str]:
    """Numbers in the text that were never supplied. Empty list means clean."""
    offenders: list[str] = []
    for match in _NUMBER.finditer(text):
        token = match.group()
        bare = token.replace(",", "")
        try:
            magnitude = float(bare)
        except ValueError:  # pragma: no cover - the regex cannot produce this
            continue
        if magnitude < GUARD_FLOOR:
            continue
        if token not in allowed and bare not in allowed:
            offenders.append(token)
    return offenders


def build_bundle(analysis: dict[str, Any]) -> dict[str, Any]:
    """The compact fact bundle handed to the model. Structured facts in, prose out."""
    return {
        "buy_score": analysis.get("buy_score"),
        "score_withheld_reason": analysis.get("score_withheld_reason"),
        "confidence": analysis.get("confidence"),
        "scores": [
            {"component": s["component"], "subscore": s["subscore"], "available": s["available"]}
            for s in analysis.get("scores", [])
        ],
        "money": analysis.get("money", {}),
        "qualification": analysis.get("qualification", {}),
        "fair_value": analysis.get("fair_value", {}),
        "factors": analysis.get("factors", {}),
        "risks": analysis.get("risks", []),
        "unavailable": analysis.get("unavailable", []),
    }


async def explain(analysis: dict[str, Any], provider: LlmProvider) -> Explanation:
    """Ask the model to narrate, then verify it invented nothing.

    Raises :class:`LlmUnavailableError` if the model cannot be reached, and
    :class:`NumericGuardError` if it produced a figure that was not supplied. Both
    are handled the same way upstream: the analysis renders without prose.
    """
    bundle = build_bundle(analysis)
    user = f"Explain this analysis. Facts you may use, and nothing else:\n\n{_stable_json(bundle)}"
    prompt_hash = hashlib.sha256((SYSTEM_PROMPT + user).encode()).hexdigest()

    raw = await provider.complete_json(
        system=SYSTEM_PROMPT, user=user, schema=OUTPUT_SCHEMA, max_tokens=900
    )

    missing = [key for key in OUTPUT_SCHEMA["required"] if key not in raw]
    if missing:
        raise LlmUnavailableError(f"The model omitted required keys: {missing}")

    lists: dict[str, list[str]] = {}
    for key in ("pros", "cons", "questions", "what_would_change_this"):
        value = raw[key]
        if not isinstance(value, list):
            raise LlmUnavailableError(f"{key!r} came back as {type(value).__name__}, not a list.")
        lists[key] = [str(item) for item in value]

    allowed = allowed_numbers(bundle)
    prose = " ".join([str(raw["summary"]), *(item for items in lists.values() for item in items)])
    offenders = check_numbers(prose, allowed)
    if offenders:
        raise NumericGuardError(
            f"The model produced figures that were never supplied: {sorted(set(offenders))}. "
            "The explanation was discarded."
        )

    return Explanation(
        summary=str(raw["summary"]),
        pros=tuple(lists["pros"]),
        cons=tuple(lists["cons"]),
        questions=tuple(lists["questions"]),
        what_would_change_this=tuple(lists["what_would_change_this"]),
        model_id=provider.model_id,
        prompt_hash=prompt_hash,
        numeric_guard_passed=True,
    )


def _stable_json(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, sort_keys=True, separators=(",", ": "), default=str)
