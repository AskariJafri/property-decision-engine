"""The explanation, as the API actually serves it.

``test_ai_runtime`` covers the explainer and its numeric guard in isolation. This
covers the part that was missing for longer: that the endpoint calls them at all,
and that every way the model can fail leaves the analysis intact.

The invariant worth stating plainly, because it is the whole design: prose is the
least important thing on the page. A model that is off, down, malformed or lying
must cost the reader an explanation and nothing else. Every test here asserts a
200 and a complete set of figures alongside whatever went wrong.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.contracts import LlmUnavailableError
from app.core.config import Settings, get_settings
from app.main import create_app

from .test_app import REQUEST

client = TestClient(create_app())

GOOD_OUTPUT: dict[str, Any] = {
    "summary": "The asking price sits inside the estimated fair-value range.",
    "pros": ["Three bedrooms meets your minimum."],
    "cons": ["Housing would take a large share of gross income."],
    "questions": ["When was the roof last replaced?"],
    "what_would_change_this": ["Adding recent comparable sales."],
}


class FakeProvider:
    """Stands in for the model. Returns a payload, or raises."""

    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self.result = result
        self.calls = 0

    @property
    def model_id(self) -> str:
        return "fake-model:test"

    async def complete_json(self, **_: Any) -> dict[str, Any]:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch):
    """Turn explanations on, and hand the route a fake model.

    ``get_settings`` is lru_cached, so the override has to replace the cached
    function rather than the environment — otherwise the first test to read
    settings fixes them for the whole session.
    """

    def _enable(result: dict[str, Any] | Exception) -> FakeProvider:
        provider = FakeProvider(result)
        settings = Settings(llm_explanations_enabled=True)
        monkeypatch.setattr("app.api.v1.routes.get_settings", lambda: settings)
        monkeypatch.setattr("app.api.v1.routes.OpenAICompatibleProvider", lambda _s: provider)
        return provider

    yield _enable
    get_settings.cache_clear()


def analyze() -> dict[str, Any]:
    response = client.post("/api/v1/properties/analyze", json=REQUEST)
    assert response.status_code == 200, response.text
    return response.json()


def assert_analysis_is_intact(body: dict[str, Any]) -> None:
    """The figures are present and complete, whatever the model did."""
    assert 0 <= body["buy_score"] <= 100
    assert body["money"]["monthly_ownership_cost_cents"] > 0
    assert body["traces"], "the working must survive any explanation failure"


class TestOff:
    def test_off_by_default_and_says_so(self):
        """A blank space where prose should be tells the reader nothing about
        whether an explanation was even attempted. Name it instead."""
        body = analyze()
        assert body["explanation"] is None
        assert "turned off" in body["explanation_unavailable_reason"]
        assert_analysis_is_intact(body)

    def test_health_reports_the_switch_not_the_base_url(self):
        """The old flag was bool(llm_base_url) on a non-empty default, so it was
        true on deployments that had never seen a model."""
        body = client.get("/api/v1/health").json()
        assert body["ai_explanations_enabled"] is False
        assert "local_model" not in body["providers_configured"]


class TestOn:
    def test_a_good_explanation_is_served_and_labelled_ai(self, enabled):
        provider = enabled(GOOD_OUTPUT)
        body = analyze()

        assert provider.calls == 1
        assert body["explanation_unavailable_reason"] is None
        explanation = body["explanation"]
        assert explanation["summary"] == GOOD_OUTPUT["summary"]
        assert explanation["pros"] == GOOD_OUTPUT["pros"]
        assert explanation["model_id"] == "fake-model:test"
        assert explanation["numeric_guard_passed"] is True
        # The reader must never mistake narration for the analysis.
        assert explanation["source"] == "ai_inferred"
        assert_analysis_is_intact(body)

    def test_an_invented_figure_discards_the_whole_explanation(self, enabled):
        """The guard is the reason a model is allowed near this at all. It never
        repairs output: a plausible invented number is worse than no prose."""
        enabled({**GOOD_OUTPUT, "summary": "Your monthly cost is $9,999,999."})
        body = analyze()

        assert body["explanation"] is None
        reason = body["explanation_unavailable_reason"]
        assert "never supplied" in reason and "9,999,999" in reason
        assert_analysis_is_intact(body)

    def test_a_model_that_is_down_costs_only_the_prose(self, enabled):
        enabled(LlmUnavailableError("The model could not be reached: connect timeout"))
        body = analyze()

        assert body["explanation"] is None
        assert "could not be reached" in body["explanation_unavailable_reason"]
        assert_analysis_is_intact(body)

    def test_an_unexpected_failure_is_contained(self, enabled):
        """Anything the explainer did not anticipate still must not surface as a
        500 on an analysis that computed perfectly well."""
        enabled(RuntimeError("something nobody predicted"))
        body = analyze()

        assert body["explanation"] is None
        assert "failed unexpectedly" in body["explanation_unavailable_reason"]
        assert_analysis_is_intact(body)

    def test_malformed_output_is_refused_rather_than_coerced(self, enabled):
        enabled({**GOOD_OUTPUT, "pros": "not a list"})
        body = analyze()

        assert body["explanation"] is None
        assert "not a list" in body["explanation_unavailable_reason"]
        assert_analysis_is_intact(body)

    def test_the_model_cannot_move_a_single_figure(self, enabled):
        """ADR 0004's core promise. The model is handed a finished analysis, so
        turning it on must change the prose and nothing else."""
        without = analyze()
        enabled(GOOD_OUTPUT)
        with_prose = analyze()

        assert with_prose["explanation"] is not None
        for field in ("buy_score", "confidence", "inputs_hash", "money", "scores", "fair_value"):
            assert with_prose[field] == without[field], field
