"""The ORS adapter, against mocked responses in the documented shape."""

from decimal import Decimal

import httpx

from app.engines.scoring.contracts import Component
from app.engines.scoring.subscores import location_subscore
from app.provenance.types import SourceClass
from app.providers.openrouteservice import OpenRouteServiceProvider

GEOCODE = {
    "features": [
        {
            "geometry": {"type": "Point", "coordinates": [-79.3832, 43.6532]},
            "properties": {"confidence": 0.9},
        }
    ]
}
ROUTE = {"routes": [{"summary": {"distance": 14200, "duration": 1620}}]}


def transport(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestUnconfigured:
    async def test_no_key_degrades_with_an_actionable_reason(self):
        provider = OpenRouteServiceProvider("")
        assert provider.configured is False
        fact = await provider.geocode("100 Queen St W, Toronto")
        assert not fact.is_available
        assert "no OpenRouteService key" in (fact.provenance.unavailable_reason or "")


class TestGeocoding:
    async def test_geojson_is_read_longitude_first(self):
        """The trap: GeoJSON is [lon, lat]. Reading it the other way puts a Toronto
        property in Somalia and still returns a plausible duration."""
        async with transport(lambda r: httpx.Response(200, json=GEOCODE)) as client:
            fact = await OpenRouteServiceProvider("k", client=client).geocode("Toronto")
        assert fact.require() == (43.6532, -79.3832)  # (lat, lon), the right way round

    async def test_the_search_is_biased_to_canada(self):
        """ "London" and "Cambridge" are both Ontario cities and both far more famous
        somewhere else."""
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(dict(request.url.params))
            return httpx.Response(200, json=GEOCODE)

        async with transport(handler) as client:
            await OpenRouteServiceProvider("k", client=client).geocode("London")
        assert seen["boundary.country"] == "CA"

    async def test_no_match_is_a_stated_absence(self):
        async with transport(lambda r: httpx.Response(200, json={"features": []})) as client:
            fact = await OpenRouteServiceProvider("k", client=client).geocode("nowhere at all")
        assert not fact.is_available
        assert "No Canadian match" in (fact.provenance.unavailable_reason or "")


class TestCommute:
    async def test_seconds_become_whole_minutes(self):
        async with transport(lambda r: httpx.Response(200, json=ROUTE)) as client:
            fact = await OpenRouteServiceProvider("k", client=client).commute(
                from_lat=43.65, from_lon=-79.38, to_lat=43.70, to_lon=-79.40
            )
        assert fact.require() == 27  # 1620s
        assert fact.unit == "minutes"

    async def test_coordinates_are_sent_longitude_first_with_a_bare_key(self):
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            captured["body"] = json.loads(request.content)
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json=ROUTE)

        async with transport(handler) as client:
            await OpenRouteServiceProvider("secret-key", client=client).commute(
                from_lat=43.65, from_lon=-79.38, to_lat=43.70, to_lon=-79.40
            )
        assert captured["body"] == {"coordinates": [[-79.38, 43.65], [-79.40, 43.70]]}
        # ORS rejects a "Bearer " prefix; the key goes in bare.
        assert captured["auth"] == "secret-key"

    async def test_transit_is_labelled_an_estimate_rather_than_passed_off(self):
        """ORS has no transit profile. Answering with a driving time is defensible;
        calling it a transit time would not be."""
        async with transport(lambda r: httpx.Response(200, json=ROUTE)) as client:
            fact = await OpenRouteServiceProvider("k", client=client).commute(
                from_lat=1, from_lon=1, to_lat=2, to_lon=2, mode="transit"
            )
        assert fact.provenance.source_class is SourceClass.ESTIMATED
        assert fact.provenance.confidence < 0.5

    async def test_an_outage_degrades_rather_than_raising(self):
        async with transport(lambda r: httpx.Response(503, json={})) as client:
            fact = await OpenRouteServiceProvider("k", client=client).commute(
                from_lat=1, from_lon=1, to_lat=2, to_lon=2
            )
        assert not fact.is_available


class TestLocationSubscore:
    def test_a_commute_inside_the_maximum_scores_well(self):
        result = location_subscore(commute_minutes=27, max_commute_minutes=45)
        assert result.available
        assert result.score is not None and result.score > 80

    def test_a_commute_far_over_the_maximum_scores_badly(self):
        result = location_subscore(commute_minutes=90, max_commute_minutes=30)
        assert result.score is not None and result.score < 30

    def test_one_input_of_two_scores_at_lower_confidence(self):
        commute_only = location_subscore(commute_minutes=27, max_commute_minutes=45)
        both = location_subscore(
            commute_minutes=27, max_commute_minutes=45, amenity_counts={"grocery": 12}
        )
        assert commute_only.confidence < both.confidence

    def test_an_estimated_transit_time_costs_further_confidence(self):
        driven = location_subscore(commute_minutes=27, max_commute_minutes=45)
        estimated = location_subscore(
            commute_minutes=27, max_commute_minutes=45, commute_is_estimated=True
        )
        assert estimated.confidence < driven.confidence
        assert any("estimated from driving" in f.sentence for f in estimated.factors)

    def test_nothing_measured_means_unavailable_with_a_reason(self):
        result = location_subscore(commute_minutes=None, max_commute_minutes=45)
        assert result.available is False
        assert result.component is Component.LOCATION
        assert "could not be measured" in (result.unavailable_reason or "")

    def test_it_scores_without_a_stated_maximum(self):
        result = location_subscore(commute_minutes=25, max_commute_minutes=None)
        assert result.available and result.score is not None
        assert result.score > Decimal("50")
