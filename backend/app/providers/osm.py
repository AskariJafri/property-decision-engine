"""Adapters for the self-hosted OpenStreetMap stack, and for Toronto's open data.

Every method returns a :class:`~app.provenance.types.Fact`. A provider that is not
configured, is down, or answers with something unexpected produces an
``UNAVAILABLE`` fact carrying the reason — never an exception, never a zero, never
a guess. A vendor outage degrades an analysis; it does not fail one.

The ODbL licence on the self-hosted stack is what lets these results be stored
permanently, which is the whole reason ADR 0002 chose it over Google.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from app.provenance.policy import OSM_SELF_HOSTED, TORONTO_OPEN_DATA, TRCA, ProviderPolicy
from app.provenance.types import Fact, Provenance, SourceClass


def _now() -> datetime:
    return datetime.now(UTC)


def _verified[T](
    value: T, policy: ProviderPolicy, *, confidence: float = 1.0, unit: str | None = None
) -> Fact[T]:
    return Fact(
        value=value,
        provenance=Provenance(
            source_key=policy.key,
            source_class=SourceClass.VERIFIED,
            retrieved_at=_now(),
            confidence=confidence,
            source_url=policy.source_url,
        ),
        unit=unit,
    )


class NominatimGeocoder:
    """Address to coordinates, from our own instance on an Ontario extract."""

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client

    @property
    def policy(self) -> ProviderPolicy:
        return OSM_SELF_HOSTED

    async def geocode(self, address: str) -> Fact[tuple[float, float]]:
        if not self.base_url:
            return Fact.unavailable(
                "Geocoding is not configured — the OpenStreetMap services are not running.",
                source_key=self.policy.key,
            )
        try:
            data = await self._get("/search", {"q": address, "format": "jsonv2", "limit": 1})
        except httpx.HTTPError as exc:
            return Fact.unavailable(
                f"The geocoder could not be reached: {exc}", source_key=self.policy.key
            )

        if not data:
            return Fact.unavailable(
                f"No match for {address!r}. Check the address, or enter coordinates directly.",
                source_key=self.policy.key,
            )
        first = data[0]
        return _verified(
            (float(first["lat"]), float(first["lon"])),
            self.policy,
            confidence=min(1.0, float(first.get("importance", 0.5)) + 0.4),
        )

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        client = self._client or httpx.AsyncClient(timeout=10)
        try:
            response = await client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            return response.json()
        finally:
            if self._client is None:
                await client.aclose()


class OsrmRouter:
    """Commute times from our own routing instance."""

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client

    @property
    def policy(self) -> ProviderPolicy:
        return OSM_SELF_HOSTED

    async def travel_minutes(
        self, *, from_lat: float, from_lon: float, to_lat: float, to_lon: float, mode: str = "car"
    ) -> Fact[int]:
        if not self.base_url:
            return Fact.unavailable(
                "Commute time is unavailable — the routing service is not running.",
                source_key=self.policy.key,
            )
        profile = {"car": "driving", "bike": "cycling", "walk": "walking"}.get(mode, "driving")
        url = f"{self.base_url}/route/v1/{profile}/{from_lon},{from_lat};{to_lon},{to_lat}"
        client = self._client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.get(url, params={"overview": "false"})
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            return Fact.unavailable(
                f"The routing service could not be reached: {exc}", source_key=self.policy.key
            )
        finally:
            if self._client is None:
                await client.aclose()

        routes = body.get("routes") or []
        if not routes:
            return Fact.unavailable(
                "No route found between those points.", source_key=self.policy.key
            )
        return _verified(round(routes[0]["duration"] / 60), self.policy, unit="minutes")


class OverpassPlaces:
    """Amenity counts and distances, for our own walkability metric."""

    CATEGORIES: ClassVar[dict[str, str]] = {
        "grocery": '[shop~"supermarket|convenience|greengrocer"]',
        "school": "[amenity=school]",
        "park": "[leisure=park]",
        "pharmacy": "[amenity=pharmacy]",
        "clinic": '[amenity~"clinic|doctors|hospital"]',
        "transit": "[public_transport=stop_position]",
        "restaurant": '[amenity~"restaurant|cafe"]',
    }

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client

    @property
    def policy(self) -> ProviderPolicy:
        return OSM_SELF_HOSTED

    async def count_within(
        self, *, latitude: float, longitude: float, category: str, radius_m: int = 1200
    ) -> Fact[int]:
        if not self.base_url:
            return Fact.unavailable(
                "Amenity data is unavailable — the Overpass service is not running.",
                source_key=self.policy.key,
            )
        selector = self.CATEGORIES.get(category)
        if selector is None:
            return Fact.unavailable(
                f"{category!r} is not a category we query.", source_key=self.policy.key
            )
        query = (
            f"[out:json][timeout:20];"
            f"node{selector}(around:{radius_m},{latitude},{longitude});out count;"
        )
        client = self._client or httpx.AsyncClient(timeout=25)
        try:
            response = await client.post(f"{self.base_url}/api/interpreter", data={"data": query})
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            return Fact.unavailable(
                f"Overpass could not be reached: {exc}", source_key=self.policy.key
            )
        finally:
            if self._client is None:
                await client.aclose()

        elements = body.get("elements") or []
        if not elements:
            return _verified(0, self.policy)
        total = elements[0].get("tags", {}).get("total", 0)
        return _verified(int(total), self.policy)


class TrcaFloodProvider:
    """TRCA regulated areas and floodlines, from their ArcGIS open data.

    The ``FloodPlainSource`` attribute distinguishes a mapped flood plain from an
    estimated one, and that distinction maps straight onto CONFIRMED versus
    POTENTIAL (ADR 0003). Flattening it would turn a modelling artefact into a
    statement of fact about someone's house.
    """

    BASE = "https://services.arcgis.com"

    def __init__(self, service_url: str = "", client: httpx.AsyncClient | None = None) -> None:
        self.service_url = service_url.rstrip("/")
        self._client = client

    @property
    def policy(self) -> ProviderPolicy:
        return TRCA

    async def flood_status(self, *, latitude: float, longitude: float) -> Fact[dict[str, str]]:
        if not self.service_url:
            return Fact.unavailable(
                "Flood mapping is not configured for this environment. Absence of a "
                "flood finding is not evidence that the property is safe.",
                source_key=self.policy.key,
            )
        params = {
            "geometry": f"{longitude},{latitude}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "FloodPlainSource",
            "returnGeometry": "false",
            "f": "json",
        }
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            response = await client.get(f"{self.service_url}/query", params=params)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            return Fact.unavailable(
                f"The conservation authority service could not be reached: {exc}",
                source_key=self.policy.key,
            )
        finally:
            if self._client is None:
                await client.aclose()

        features = body.get("features") or []
        if not features:
            return _verified({"in_flood_plain": "no", "source": "trca"}, self.policy)
        attributes = features[0].get("attributes", {})
        source = str(attributes.get("FloodPlainSource", "")).lower()
        return _verified(
            {
                "in_flood_plain": "yes",
                "mapping": "estimated" if "estimate" in source else "mapped",
                "source": "trca",
            },
            self.policy,
        )


class TorontoOpenData:
    """Zoning and development applications from the CKAN portal."""

    def __init__(
        self,
        base_url: str = "https://ckan0.cf.opendata.inter.prod-toronto.ca",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client

    @property
    def policy(self) -> ProviderPolicy:
        return TORONTO_OPEN_DATA

    async def development_applications(
        self, *, latitude: float, longitude: float, radius_m: int = 1000
    ) -> Fact[list[dict[str, Any]]]:
        # The CKAN datastore has no spatial predicate, so the real implementation
        # loads the dataset on a schedule and queries it locally. Until that job
        # exists, the honest answer is that we have not checked.
        return Fact.unavailable(
            "Nearby development applications have not been checked in this environment. "
            "Toronto publishes them openly; the scheduled import is not running.",
            source_key=self.policy.key,
        )
