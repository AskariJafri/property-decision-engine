"""Reading a listing without a model at all.

Most listings state their facts in a handful of predictable shapes — "$849,000",
"3 bed", "1,450 sq ft", "built in 1998". A regex pass catches those exactly,
deterministically, and with the matched span as evidence, which means the common
case needs no model, no GPU and no network.

This runs **first**. The language model is the fallback for what patterns cannot
reach — prose descriptions, unusual phrasing, fields buried in a paragraph — which
inverts the usual arrangement and is the right way round for a product whose whole
claim is that its numbers are traceable. A regex match can be shown to the user as
the exact characters it came from; a model's answer can only be asserted.

Every value still goes through :func:`~app.ingestion.listing.validate` and still
requires the user to confirm it.
"""

from __future__ import annotations

import re

from app.ingestion.listing import ExtractionResult, validate

#: The decimals live INSIDE the capture group. Leaving them outside silently
#: truncates "$612.50" to $612 — half a dollar a month, in a figure the whole
#: affordability calculation rests on.
_MONEY = r"\$?\s*([\d][\d,]{2,}(?:\.\d{1,2})?)"

#: Each pattern names the field it fills. Order matters only within a field: the
#: first pattern that matches wins, so the more specific ones come first.
PATTERNS: dict[str, tuple[str, ...]] = {
    "listing_price": (
        rf"(?:asking|list(?:ed|ing)?|offered at|price[d]?(?: at)?)\D{{0,12}}{_MONEY}",
        rf"{_MONEY}\s*(?:asking|list price)",
    ),
    "bedrooms": (
        r"(\d+)\s*(?:\+\s*\d+\s*)?(?:bed(?:room)?s?\b|\bbr\b|\bbd\b)",
        r"bed(?:room)?s?\D{0,6}(\d+)",
    ),
    "bathrooms": (
        r"(\d+(?:\.\d)?)\s*(?:bath(?:room)?s?\b|\bba\b)",
        r"bath(?:room)?s?\D{0,6}(\d+(?:\.\d)?)",
    ),
    "square_feet": (
        r"([\d,]{3,6})\s*(?:sq\.?\s*(?:ft|feet)|square\s*feet|sqft)",
        r"(?:sq\.?\s*ft|size)\D{0,8}([\d,]{3,6})",
    ),
    "year_built": (
        r"(?:built|constructed|vintage|year built)\D{0,10}(\d{4})",
        r"\b(19\d{2}|20\d{2})\s*(?:build|construction)\b",
    ),
    "annual_property_tax": (
        rf"(?:property\s*tax(?:es)?|annual\s*tax(?:es)?|taxes)\D{{0,15}}{_MONEY}",
    ),
    "monthly_condo_fee": (
        rf"(?:condo\s*fee|maintenance\s*fee|common\s*element)\w*\D{{0,15}}{_MONEY}",
    ),
    "parking_spaces": (
        r"(\d+)\s*(?:car\s*)?(?:parking|garage)\b",
        r"parking\D{0,8}(\d+)",
    ),
}

#: Written-out counts, because "two car parking" and "three bedrooms" are ordinary
#: listing English and a digits-only pass silently drops them.
WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
}
WORD_FIELDS = ("bedrooms", "bathrooms", "parking_spaces")
WORD_NOUNS = {
    "bedrooms": r"bed(?:room)?s?",
    "bathrooms": r"bath(?:room)?s?",
    "parking_spaces": r"(?:car\s*)?(?:parking|garage)",
}


def parse(text: str) -> ExtractionResult:
    """Pull what the patterns can reach, with the matched span as evidence."""
    raw: dict[str, object] = {}
    spans: dict[str, str] = {}
    lowered = text.lower()

    for field, patterns in PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, lowered, re.IGNORECASE)
            if match:
                raw[field] = match.group(1).replace(",", "")
                spans[field] = _span(text, match.start(), match.end())
                break

    for field in WORD_FIELDS:
        if field in raw:
            continue
        noun = WORD_NOUNS[field]
        for word, value in WORD_NUMBERS.items():
            match = re.search(rf"\b{word}\s*(?:\w+\s*)?{noun}\b", lowered)
            if match:
                raw[field] = value
                spans[field] = _span(text, match.start(), match.end())
                break

    result = validate(raw)
    result.model_id = "deterministic:patterns"
    result.evidence = {field: spans[field] for field in result.fields if field in spans}
    return result


def _span(text: str, start: int, end: int, window: int = 30) -> str:
    return text[max(0, start - window) : end + window].replace("\n", " ").strip()
