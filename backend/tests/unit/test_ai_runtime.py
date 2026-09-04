"""The AI layer, exercised against a fake model — no local server required."""

from typing import Any

import pytest

from app.ai.contracts import LlmUnavailableError
from app.ai.explainer import (
    NumericGuardError,
    allowed_numbers,
    build_bundle,
    check_numbers,
    explain,
)

ANALYSIS: dict[str, Any] = {
    "buy_score": 78,
    "score_withheld_reason": None,
    "confidence": 0.71,
    "scores": [{"component": "affordability", "subscore": 84.0, "available": True}],
    "money": {
        "monthly_ownership_cost_cents": 574762,
        "closing_costs_cents": 2459089,
        "cash_required_cents": 14459089,
    },
    "qualification": {"may_qualify": True, "gds": 0.341},
    "fair_value": {"low_cents": 82000000, "high_cents": 84500000},
    "factors": {"positive": [], "negative": []},
    "risks": [],
    "unavailable": [{"component": "location", "reason": "OSM services not configured"}],
}


class FakeModel:
    """Returns whatever it was told to. The point is the guard, not the model."""

    def __init__(self, payload: dict[str, Any] | Exception):
        self.payload = payload
        self.calls = 0

    @property
    def model_id(self) -> str:
        return "llama3.1:8b-instruct-q4_K_M"

    async def complete_json(self, **_: Any) -> dict[str, Any]:
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def good_output(
    summary: str = "The monthly cost is 5,747.62 and closing needs 24,590.89.",
) -> dict[str, Any]:
    return {
        "summary": summary,
        "pros": ["Debt service clears the guidelines."],
        "cons": ["Location could not be assessed."],
        "questions": ["When was the roof replaced?"],
        "what_would_change_this": ["A rate rise of one point."],
    }


class TestNumericGuard:
    def test_supplied_figures_are_allowed_in_dollars_or_cents(self):
        allowed = allowed_numbers(build_bundle(ANALYSIS))
        assert "574762" in allowed  # cents, as supplied
        assert "5,747.62" in allowed  # dollars, as a human would write them
        assert "82000000" in allowed and "820,000" in allowed

    def test_an_invented_figure_is_caught(self):
        allowed = allowed_numbers(build_bundle(ANALYSIS))
        assert check_numbers("Expect about 6,200 a month.", allowed) == ["6,200"]

    def test_ordinary_small_numbers_are_not_policed(self):
        """Guarding "three bedrooms" or "the first 12 months" would reject every
        readable sentence, so the guard covers figures large enough to mislead."""
        allowed = allowed_numbers(build_bundle(ANALYSIS))
        assert check_numbers("It has 3 bedrooms and 2.5 bathrooms.", allowed) == []

    async def test_a_hallucinating_model_fails_closed(self):
        model = FakeModel(good_output("Your monthly cost will be about 6,300 dollars."))
        with pytest.raises(NumericGuardError, match="never supplied"):
            await explain(ANALYSIS, model)

    async def test_a_faithful_model_passes(self):
        result = await explain(ANALYSIS, FakeModel(good_output()))
        assert result.numeric_guard_passed
        assert result.model_id == "llama3.1:8b-instruct-q4_K_M"
        assert len(result.prompt_hash) == 64
        assert result.questions


class TestDegradation:
    async def test_a_missing_key_is_a_discard_not_a_repair(self):
        broken = good_output()
        del broken["questions"]
        with pytest.raises(LlmUnavailableError, match="omitted required keys"):
            await explain(ANALYSIS, FakeModel(broken))

    async def test_an_unreachable_model_raises_the_degradation_error(self):
        model = FakeModel(LlmUnavailableError("connection refused"))
        with pytest.raises(LlmUnavailableError):
            await explain(ANALYSIS, model)


class TestBundle:
    def test_the_model_only_ever_sees_finished_facts(self):
        bundle = build_bundle(ANALYSIS)
        assert set(bundle) <= {
            "buy_score",
            "score_withheld_reason",
            "confidence",
            "scores",
            "money",
            "qualification",
            "fair_value",
            "factors",
            "risks",
            "unavailable",
        }
        # No trace, no raw inputs, nothing it could recompute from.
        assert "traces" not in bundle

    def test_unavailable_items_travel_into_the_prompt(self):
        assert build_bundle(ANALYSIS)["unavailable"][0]["component"] == "location"
