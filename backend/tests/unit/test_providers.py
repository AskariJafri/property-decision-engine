"""Provider adapters degrade; they do not fail an analysis."""

from typing import Any

import httpx

from app.provenance.policy import LicenceClass
from app.providers.osm import (
    NominatimGeocoder,
    OsrmRouter,
    OverpassPlaces,
    TorontoOpenData,
    TrcaFloodProvider,
)


def transport(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestUnconfigured:
    """The default state of a fresh clone: nothing running, nothing broken."""

    async def test_geocoder_says_it_is_not_configured(self):
        fact = await NominatimGeocoder("").geocode("100 Queen St W, Toronto")
        assert not fact.is_available
        assert "not configured" in (fact.provenance.unavailable_reason or "")

    async def test_router_says_it_is_not_running(self):
        fact = await OsrmRouter("").travel_minutes(
            from_lat=43.65, from_lon=-79.38, to_lat=43.70, to_lon=-79.40, mode="car"
        )
        assert not fact.is_available

    async def test_flood_absence_is_never_reported_as_safety(self):
        """The sharpest test in the product: 'we did not check' must not read as
        'this house does not flood'."""
        fact = await TrcaFloodProvider("").flood_status(latitude=43.65, longitude=-79.38)
        assert not fact.is_available
        reason = fact.provenance.unavailable_reason or ""
        assert "not evidence that the property is safe" in reason


class TestFailure:
    async def test_an_unreachable_service_becomes_an_unavailable_fact(self):
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        async with transport(boom) as client:
            fact = await NominatimGeocoder("http://localhost:8081", client).geocode("x")
        assert not fact.is_available
        assert "could not be reached" in (fact.provenance.unavailable_reason or "")

    async def test_a_five_hundred_is_not_an_exception(self):
        async with transport(lambda r: httpx.Response(500, json={})) as client:
            fact = await OsrmRouter("http://localhost:5000", client).travel_minutes(
                from_lat=1, from_lon=1, to_lat=2, to_lon=2, mode="car"
            )
        assert not fact.is_available


class TestSuccess:
    async def test_geocoding_returns_coordinates_that_may_be_stored(self):
        payload = [{"lat": "43.6532", "lon": "-79.3832", "importance": 0.6}]
        async with transport(lambda r: httpx.Response(200, json=payload)) as client:
            fact = await NominatimGeocoder("http://localhost:8081", client).geocode("Toronto")
        assert fact.is_available
        assert fact.require() == (43.6532, -79.3832)
        # ODbL: unlike Google, this may be kept.
        assert fact.provenance.source_key == "src_osm_self_hosted"

    async def test_routing_returns_whole_minutes(self):
        payload = {"routes": [{"duration": 1500}]}
        async with transport(lambda r: httpx.Response(200, json=payload)) as client:
            fact = await OsrmRouter("http://localhost:5000", client).travel_minutes(
                from_lat=1, from_lon=1, to_lat=2, to_lon=2, mode="car"
            )
        assert fact.require() == 25
        assert fact.unit == "minutes"

    async def test_amenity_counts_come_back_as_integers(self):
        payload = {"elements": [{"tags": {"total": "7"}}]}
        async with transport(lambda r: httpx.Response(200, json=payload)) as client:
            fact = await OverpassPlaces("http://localhost:8082", client).count_within(
                latitude=43.65, longitude=-79.38, category="grocery"
            )
        assert fact.require() == 7

    async def test_an_unknown_category_is_refused_rather_than_queried(self):
        fact = await OverpassPlaces("http://localhost:8082").count_within(
            latitude=1, longitude=1, category="casinos"
        )
        assert not fact.is_available


class TestFloodSemantics:
    async def _status(self, features: list[dict[str, Any]]):
        payload = {"features": features}
        async with transport(lambda r: httpx.Response(200, json=payload)) as client:
            return await TrcaFloodProvider(
                "https://example.invalid/FeatureServer/0", client
            ).flood_status(latitude=43.65, longitude=-79.38)

    async def test_outside_every_polygon_is_a_finding(self):
        fact = await self._status([])
        assert fact.require()["in_flood_plain"] == "no"

    async def test_a_mapped_plain_and_an_estimated_one_stay_distinguishable(self):
        mapped = await self._status([{"attributes": {"FloodPlainSource": "Flood Plain Mapping"}}])
        estimated = await self._status(
            [{"attributes": {"FloodPlainSource": "Estimated Flood Plain"}}]
        )
        assert mapped.require()["mapping"] == "mapped"
        assert estimated.require()["mapping"] == "estimated"


class TestLicensing:
    def test_every_adapter_declares_a_usable_licence(self):
        adapters = [
            NominatimGeocoder(""),
            OsrmRouter(""),
            OverpassPlaces(""),
            TrcaFloodProvider(""),
            TorontoOpenData(),
        ]
        for adapter in adapters:
            assert adapter.policy.licence_class is LicenceClass.OPEN
            assert adapter.policy.may_store_values is True
