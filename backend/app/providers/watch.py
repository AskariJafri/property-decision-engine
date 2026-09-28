"""Where Property Watch gets its updates from.

Today, from the user. There is no automated listing source this product may use:
REALTOR.ca and the consumer portals prohibit automated collection, and
*Century 21 Canada v. Rogers*, 2011 BCSC 1196 held those terms enforceable
(ADR 0002 §2). So the only registered provider is ``manual`` — the buyer tells us
the new price or status they saw — and the product says so plainly rather than
implying a monitoring service that does not exist.

The protocol is here so a licensed feed (a brokerage VOW/IDX relationship, a
board data licence) can be added later as a new class and a registry entry, with
the scheduled refresh in ``api/v1/watch.py`` already calling it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ListingSnapshot:
    price_cents: int | None
    listing_status: str | None
    days_on_market: int | None
    source_key: str


class ListingWatchProvider(Protocol):
    key: str
    automated: bool
    description: str

    async def fetch(self, reference: str) -> ListingSnapshot | None:
        """The current state of a listing, or None if it cannot be determined."""
        ...


class ManualProvider:
    key = "manual"
    automated = False
    description = (
        "You enter changes you see — a new price, a status change — and the analysis is "
        "recalculated. Automatic monitoring needs a licensed listing feed, which is not "
        "connected."
    )

    async def fetch(self, reference: str) -> ListingSnapshot | None:
        return None


PROVIDERS: dict[str, ListingWatchProvider] = {"manual": ManualProvider()}


def automated_providers() -> list[ListingWatchProvider]:
    return [p for p in PROVIDERS.values() if p.automated]
