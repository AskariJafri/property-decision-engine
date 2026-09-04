"""Turning a document the user already has into structured, confirmed fields.

The pipeline is deliberately blunt about trust:

    upload or paste  ->  model extracts  ->  strict validation  ->  USER CONFIRMS  ->  stored

Nothing reaches ``property_attributes`` before that confirmation step. The model is
reading marketing copy written by someone with an interest in the outcome, so its
output is a **draft for a human**, never a fact.

We never fetch a URL (ADR 0002 §2). The user uploads what they already have, or
pastes the text. A ``source_url`` may be recorded for their reference and is not
retrieved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.ai.contracts import LlmProvider, LlmUnavailableError

SYSTEM_PROMPT = """You extract structured facts from a real estate listing.

Rules:
- Extract ONLY what the text states. Never infer, never estimate, never fill gaps.
- Omit any field the listing does not state. An absent field is correct; a guessed one is not.
- Prices and fees in Canadian dollars as plain numbers, no symbols or commas.
- Return JSON only.
"""

EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "address": {"type": "string"},
        "listing_price": {"type": "number"},
        "bedrooms": {"type": "integer"},
        "bathrooms": {"type": "number"},
        "square_feet": {"type": "integer"},
        "year_built": {"type": "integer"},
        "property_kind": {"type": "string"},
        "annual_property_tax": {"type": "number"},
        "monthly_condo_fee": {"type": "number"},
        "parking_spaces": {"type": "integer"},
    },
}

#: Bounds that reject nonsense before a human ever sees it. Deliberately wide: the
#: job is to catch a decimal point in the wrong place, not to second-guess an
#: unusual property.
BOUNDS: dict[str, tuple[float, float]] = {
    "listing_price": (50_000, 50_000_000),
    "bedrooms": (0, 20),
    "bathrooms": (0, 20),
    "square_feet": (100, 30_000),
    "year_built": (1700, 2100),
    "annual_property_tax": (0, 500_000),
    "monthly_condo_fee": (0, 10_000),
    "parking_spaces": (0, 20),
}

TEXT_FIELDS = {"address", "property_kind"}
MONEY_FIELDS = {"listing_price", "annual_property_tax", "monthly_condo_fee"}


@dataclass(slots=True)
class ExtractionResult:
    fields: dict[str, Any] = field(default_factory=dict)
    rejected: dict[str, str] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)
    model_id: str = ""
    requires_confirmation: bool = True

    def as_cents(self) -> dict[str, int]:
        """Money fields as integer cents, ready for the analyze request."""
        return {
            f"{name}_cents": round(float(self.fields[name]) * 100).__int__()
            for name in MONEY_FIELDS
            if name in self.fields
        }


def validate(raw: dict[str, Any]) -> ExtractionResult:
    """Keep what is in range and typed; reject the rest with a reason.

    Rejection is not repair. A listing price of ``85`` is dropped and reported, not
    multiplied by ten thousand because that is probably what was meant.
    """
    result = ExtractionResult()
    for name, value in raw.items():
        if name not in EXTRACTION_SCHEMA["properties"]:
            result.rejected[name] = "not a field we extract"
            continue
        if name in TEXT_FIELDS:
            if isinstance(value, str) and value.strip():
                result.fields[name] = value.strip()
            else:
                result.rejected[name] = "empty or not text"
            continue
        try:
            number = float(str(value).replace(",", "").replace("$", ""))
        except (TypeError, ValueError):
            result.rejected[name] = f"{value!r} is not a number"
            continue
        low, high = BOUNDS[name]
        if not low <= number <= high:
            result.rejected[name] = (
                f"{number:,.0f} is outside the plausible range {low:,.0f} to {high:,.0f}"
            )
            continue
        # Counts and years are integers; money and bathrooms are not. Truncating a
        # $612.50 condo fee to $612 loses fifty cents a month, every month, in a
        # figure the whole affordability calculation rests on.
        keep_decimals = name in MONEY_FIELDS or name == "bathrooms"
        result.fields[name] = number if keep_decimals else int(number)
    return result


async def extract(*, text: str, provider: LlmProvider, max_chars: int = 12_000) -> ExtractionResult:
    """Extract, validate, anchor in the source, and hand back a draft to confirm."""
    if not text.strip():
        raise LlmUnavailableError("There is nothing to extract from an empty document.")

    raw = await provider.complete_json(
        system=SYSTEM_PROMPT,
        user=f"Listing text:\n\n{text[:max_chars]}",
        schema=EXTRACTION_SCHEMA,
        max_tokens=700,
    )
    result = validate(raw)
    result.model_id = provider.model_id

    # Anchor each number in the source text. A figure the document does not contain
    # is a figure the model invented, and it is dropped rather than shown.
    for name, value in list(result.fields.items()):
        if not isinstance(value, int | float) or isinstance(value, bool):
            continue
        plain = str(int(value)) if float(value).is_integer() else str(value)
        grouped = f"{int(value):,}" if float(value).is_integer() else plain
        if plain in text or grouped in text:
            result.evidence[name] = _span(text, plain if plain in text else grouped)
        else:
            result.rejected[name] = (
                f"{value} does not appear in the document; dropped rather than trusted"
            )
            del result.fields[name]
    return result


def _span(text: str, needle: str, window: int = 40) -> str:
    match = re.search(re.escape(needle), text)
    if not match:
        return ""
    start = max(0, match.start() - window)
    return text[start : match.end() + window].replace("\n", " ").strip()
