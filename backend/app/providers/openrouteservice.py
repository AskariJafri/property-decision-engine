"""OpenRouteService: geocoding and commute times on a free key.

ADR 0002 names this the development stopgap — 2,500 requests a day, no
infrastructure, enough to make the Location score real before the self-hosted OSM
box exists. The self-hosted stack is still the production answer; this is what
lets someone see the feature working the same afternoon they get a key.

Two API details that are easy to get wrong and expensive to get wrong quietly:

* coordinates are **longitude first**, so ``[lon, lat]``. Swapping them puts a
  Toronto property in Somalia and still returns a plausible-looking duration.
* the API key goes in a bare ``Authorization`` header with **no ``Bearer``
  prefix**.

Deliberately absent: the POI endpoint. Its category taxonomy could not be
verified against current documentation, and an amenity count built on a guessed
taxonomy would be a wrong number wearing a confident label. Amenities come from
Overpass when the self-hosted stack is up, and are honestly unavailable until then.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.provenance.policy import OPENROUTESERVICE, ProviderPolicy
from app.provenance.types import Fact, Provenance, SourceClass

#: ORS profile names for the commute modes we offer.
PROFILES = {
    "car": "driving-car",
    "transit": "driving-car",  # ORS has no transit profile; see the note in commute()
    "bike": "cycling-regular",
    "walk": "foot-walking",
}


def _verified[T](value: T, *, confidence: float = 1.0, unit: str | None = None) -> Fact[T]:
    return Fact(
        value=value,
        provenance=Provenance(
            source_key=OPENROUTESERVICE.key,
            source_class=SourceClass.VERIFIED,
            retrieved_at=datetime.now(UTC),
            confidence=confidence,
            source_url=OPENROUTESERVICE.source_url,
        ),
        unit=unit,
    )


class OpenRouteServiceProvider:
    """Geocoding and routing against the hosted free tier."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openrouteservice.org",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = client

    @property
    def policy(self) -> ProviderPolicy:
        return OPENROUTESERVICE

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def geocode(self, address: str) -> Fact[tuple[float, float]]:
        """Address to ``(latitude, longitude)``.

        Biased to Canada, because "Cambridge" and "London" are both Ontario cities
        and both far more famous somewhere else.
        """
        if not self.configured:
            return Fact.unavailable(
                "Geocoding is unavailable: no OpenRouteService key is configured and "
                "the self-hosted geocoder is not running.",
                source_key=self.policy.key,
            )
        try:
            body = await self._get(
                "/geocode/search",
                {"api_key": self.api_key, "text": address, "boundary.country": "CA", "size": 1},
            )
        except httpx.HTTPStatusError as exc:
            return Fact.unavailable(self._explain(exc), source_key=self.policy.key)
        except httpx.HTTPError as exc:
            return Fact.unavailable(
                f"The geocoding service could not be reached: {exc.__class__.__name__}.",
                source_key=self.policy.key,
            )

        features = body.get("features") or []
        if not features:
            return Fact.unavailable(
                f"No Canadian match for {address!r}. Check the address, including the city.",
                source_key=self.policy.key,
            )
        lon, lat = features[0]["geometry"]["coordinates"]  # GeoJSON: lon first
        confidence = float(features[0].get("properties", {}).get("confidence", 0.7))
        return _verified((float(lat), float(lon)), confidence=min(1.0, confidence))

    async def commute(
        self,
        *,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        mode: str = "car",
    ) -> Fact[int]:
        """Door-to-door travel time in whole minutes.

        Note on transit: ORS has no public-transport profile, so a transit request
        is answered by the driving profile and the result is labelled an estimate
        rather than silently passed off as a transit time. A real transit number
        needs GTFS, which arrives with the self-hosted stack.
        """
        if not self.configured:
            return Fact.unavailable(
                "Commute time is unavailable: no OpenRouteService key is configured "
                "and the self-hosted router is not running.",
                source_key=self.policy.key,
            )

        profile = PROFILES.get(mode, "driving-car")
        try:
            body = await self._post(
                f"/v2/directions/{profile}/json",
                # Longitude first. Swapping these returns a plausible number for
                # entirely the wrong place, which is the worst kind of wrong.
                {"coordinates": [[from_lon, from_lat], [to_lon, to_lat]]},
            )
        except httpx.HTTPStatusError as exc:
            return Fact.unavailable(
                f"No commute could be calculated: {self._explain(exc)}",
                source_key=self.policy.key,
            )
        except httpx.HTTPError as exc:
            return Fact.unavailable(
                f"The routing service could not be reached: {exc.__class__.__name__}.",
                source_key=self.policy.key,
            )

        routes = body.get("routes") or []
        if not routes:
            return Fact.unavailable(
                "No route was found between the property and your work address.",
                source_key=self.policy.key,
            )
        seconds = routes[0].get("summary", {}).get("duration")
        if seconds is None:
            return Fact.unavailable(
                "The routing service returned a route with no duration.",
                source_key=self.policy.key,
            )

        minutes = round(float(seconds) / 60)
        if mode == "transit":
            # Honest about the substitution rather than quietly wrong.
            return Fact(
                value=minutes,
                provenance=Provenance(
                    source_key=self.policy.key,
                    source_class=SourceClass.ESTIMATED,
                    retrieved_at=datetime.now(UTC),
                    confidence=0.4,
                    source_url=self.policy.source_url,
                ),
                unit="minutes",
            )
        return _verified(minutes, unit="minutes")

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            response = await client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            return dict(response.json())
        finally:
            if self._client is None:
                await client.aclose()

    @staticmethod
    def _explain(exc: httpx.HTTPStatusError) -> str:
        """Turn an ORS error response into something a buyer can act on.

        ORS answers "no route between these points" with HTTP 404 and an error body,
        not with a 200 and an empty list. Treating that as a transport failure told
        the user the service could not be reached — which was false, and came with a
        raw MDN link attached.
        """
        try:
            error = exc.response.json().get("error", {})
            message = error.get("message") if isinstance(error, dict) else str(error)
        except ValueError:
            message = None
        if exc.response.status_code in (404, 413) and message:
            if "routable point" in str(message).lower():
                # Geocoding a bare city name lands on a centroid that may be
                # nowhere near a road. The fix is a street address, so say that
                # rather than quoting coordinates at a home buyer.
                return (
                    "One of the addresses did not resolve to a point on the road "
                    "network. Try a full street address rather than just a city."
                )
            return str(message)
        if exc.response.status_code in (401, 403):
            return "OpenRouteService rejected the API key. Check PDE_ORS_API_KEY."
        if exc.response.status_code == 429:
            return (
                "The OpenRouteService free tier is out of requests for today "
                "(2,500 per day). Commute will work again tomorrow."
            )
        return f"OpenRouteService returned {exc.response.status_code}" + (
            f": {message}" if message else "."
        )

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=25)
        try:
            response = await client.post(
                f"{self.base_url}{path}",
                json=body,
                # Bare key, no "Bearer" prefix — ORS rejects the prefixed form.
                headers={"Authorization": self.api_key, "Content-Type": "application/json"},
            )
            response.raise_for_status()
            return dict(response.json())
        finally:
            if self._client is None:
                await client.aclose()
