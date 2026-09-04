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

from app.ingestion.listing import BOUNDS, ExtractionResult, validate

#: The decimals live INSIDE the capture group. Leaving them outside silently
#: truncates "$612.50" to $612 — half a dollar a month, in a figure the whole
#: affordability calculation rests on.
_MONEY = r"\$?\s*([\d][\d,]{2,}(?:\.\d{1,2})?)"

#: Each pattern names the field it fills. Within a field the first match wins, so
#: the more specific patterns come first.
#:
#: **Label-first patterns come before digit-first ones**, and the digit-first ones
#: allow only spaces and tabs rather than any whitespace. A digit-first pattern
#: using ``\s*`` reaches backwards across a line break: given "Price: $1,299,000"
#: followed by "Bedrooms: 4", it took the trailing zero of the price and reported
#: bedrooms=0, after which bathrooms picked up the 4 — every field shifted by one
#: and every one of them confidently wrong. A missing value is recoverable; a
#: wrong one that looks right is not.
PATTERNS: dict[str, tuple[str, ...]] = {
    "listing_price": (
        # A reduced listing states both prices. The current one is what a buyer
        # pays, so it is matched first; otherwise "was $999,000, now $899,900"
        # takes the number the seller gave up on.
        rf"(?:now|reduced to|new price|revised to)\D{{0,12}}{_MONEY}",
        rf"(?:asking|list(?:ed|ing)?|offered at|price[d]?(?: at)?)\D{{0,12}}{_MONEY}",
        rf"{_MONEY}\s*(?:asking|list price)",
    ),
    "bedrooms": (
        r"bed(?:room)?s?\s*[:=\-]\s*(\d+)",
        r"(\d+)(?:\s*\+\s*\d+)?[ \t]*(?:bed(?:room)?s?\b|\bbr\b|\bbd\b)",
    ),
    "bathrooms": (
        r"bath(?:room)?s?\s*[:=\-]\s*(\d+(?:\.\d)?)",
        r"(\d+(?:\.\d)?)[ \t]*(?:bath(?:room)?s?\b|\bba\b)",
    ),
    "square_feet": (
        r"(?:sq\.?\s*ft|square\s*feet|sqft|size)\s*[:=\-]\s*(?:approx\.?\s*)?([\d,]{3,6})",
        r"([\d,]{3,6})[ \t]*(?:sq\.?[ \t]*(?:ft|feet)|square[ \t]*feet|sqft)",
    ),
    "year_built": (
        r"(?:built|constructed|vintage|year built)\D{0,10}(\d{4})",
        r"\b(19\d{2}|20\d{2})\s*(?:build|construction)\b",
    ),
    "annual_property_tax": (
        rf"(?:property\s*tax(?:es)?|annual\s*tax(?:es)?|taxes)\D{{0,15}}{_MONEY}",
    ),
    "monthly_condo_fee": (
        rf"(?:condo\s*fee|maint(?:enance)?\.?\s*fee|common\s*element\w*\s*fee|"
        rf"strata\s*fee)\D{{0,15}}{_MONEY}",
    ),
    "parking_spaces": (
        r"parking\s*[:=\-]\s*(\d+)",
        r"(\d+)[ \t]*(?:car\s*)?(?:parking|garage)\b",
    ),
}

#: A listing usually leads with its price and often gives it no label at all —
#: just "$899,900" across the top. Used only when no labelled pattern matched, and
#: required to carry a dollar sign so it cannot mistake a floor area or a year for
#: a price. The first plausible figure wins and its evidence span is shown, so a
#: "reduced from" price is visible to the user rather than silently chosen.
_BARE_PRICE = re.compile(r"\$\s*([\d][\d,]{2,}(?:\.\d{1,2})?)")

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

    if "listing_price" not in raw:
        low, high = BOUNDS["listing_price"]
        for match in _BARE_PRICE.finditer(text):
            candidate = float(match.group(1).replace(",", ""))
            if low <= candidate <= high:
                raw["listing_price"] = match.group(1).replace(",", "")
                spans["listing_price"] = _span(text, match.start(), match.end())
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
