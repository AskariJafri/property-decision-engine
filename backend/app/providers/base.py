"""Provider adapters: one Protocol per external source, each carrying its licence.

Every adapter exposes a :class:`~app.provenance.policy.ProviderPolicy`, which is
how the provenance repository knows whether it may persist what the adapter
returned. An adapter for a prohibited source cannot be written usefully — the
policy raises before anything reaches the database — and that is deliberate.

Adapters return :class:`~app.provenance.types.Fact` values, never bare numbers,
so a provider failure becomes an explicit ``UNAVAILABLE`` with a reason instead
of a zero, a ``None`` or an exception that a caller might swallow. A vendor being
down degrades an analysis; it does not fail one.

In the free stack (ADR 0002) the geocoding, routing and places providers point at
our own Nominatim, OSRM and Overpass instances running on an Ontario extract.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.core.money import Cents
from app.provenance.policy import ProviderPolicy
from app.provenance.types import Fact


@runtime_checkable
class Provider(Protocol):
    """Everything an adapter must expose, whatever it fetches."""

    @property
    def policy(self) -> ProviderPolicy: ...


class GeocodingProvider(Provider, Protocol):
    """Address to coordinates. Self-hosted Nominatim; ODbL, so results are storable."""

    async def geocode(self, address: str) -> Fact[tuple[float, float]]: ...

    async def reverse(self, latitude: float, longitude: float) -> Fact[str]: ...


class RoutingProvider(Provider, Protocol):
    """Commute times. Self-hosted OSRM or Valhalla."""

    async def travel_minutes(
        self,
        *,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        mode: str,
    ) -> Fact[int]: ...


class PlacesProvider(Provider, Protocol):
    """Nearby amenities. Self-hosted Overpass over OSM."""

    async def nearest(
        self, *, latitude: float, longitude: float, category: str, radius_m: int
    ) -> Fact[int]:
        """Distance in metres to the nearest feature of a category."""

    async def count_within(
        self, *, latitude: float, longitude: float, category: str, radius_m: int
    ) -> Fact[int]: ...


class MortgageRateProvider(Provider, Protocol):
    """Bank of Canada Valet. Posted rates, which are not contract rates — the
    user's own quote always wins, and the UI says which is in play."""

    async def posted_rate(self, *, term_years: int, as_of: date) -> Fact[Decimal]: ...


class MarketDataProvider(Provider, Protocol):
    """Dated market context. Never a constant in code."""

    async def snapshot(self, *, jurisdiction: str, as_of: date) -> Fact[dict[str, Decimal]]: ...


class RentalDataProvider(Provider, Protocol):
    """CMHC Rental Market Survey: the rent input to the Investment Score."""

    async def average_rent(
        self, *, jurisdiction: str, bedrooms: int, as_of: date
    ) -> Fact[Cents]: ...


class MunicipalDataProvider(Provider, Protocol):
    """Zoning, development applications, property boundaries.

    Toronto is the first implementation, not the shape of the interface — the
    second municipality will have a different portal and a different licence
    (ADR 0003).
    """

    async def zoning(self, *, latitude: float, longitude: float) -> Fact[str]: ...

    async def development_applications(
        self, *, latitude: float, longitude: float, radius_m: int
    ) -> Fact[list[dict[str, object]]]: ...


class FloodRiskProvider(Provider, Protocol):
    """Conservation authority mapping. TRCA for the Toronto pilot.

    Outside mapped coverage the answer is an ``UNAVAILABLE`` Fact, which the risk
    engine turns into an ``UNKNOWN`` flag. It must never become "no flood risk".
    """

    async def flood_status(self, *, latitude: float, longitude: float) -> Fact[dict[str, str]]: ...


class SchoolDataProvider(Provider, Protocol):
    """EQAO results and school locations.

    There is deliberately no ``catchment()`` method: attendance boundaries are
    held by individual boards and are not published provincially, so the product
    says *nearby schools*, never *your school*.
    """

    async def nearby_schools(
        self, *, latitude: float, longitude: float, radius_m: int
    ) -> Fact[list[dict[str, object]]]: ...


class ListingExtractionProvider(Provider, Protocol):
    """LLM extraction from a document the user supplied.

    Never fetches a URL. The user uploads or pastes what they already have
    (ADR 0002 §2), and nothing extracted is stored until they confirm it.
    """

    async def extract(self, *, content: bytes, media_type: str) -> Fact[dict[str, object]]: ...
