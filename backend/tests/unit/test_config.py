"""Settings must survive the environment a deployment platform actually gives it."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


class TestBlankEnvironmentVariables:
    def test_a_blank_numeric_variable_falls_back_to_its_default(self):
        """A blank PDE_LLM_SEED once took the whole application down at import
        with five validation errors and a 500 that named none of them."""
        settings = Settings(llm_seed="", llm_temperature="", debug="")  # type: ignore[arg-type]
        assert settings.llm_seed == 7
        assert settings.llm_temperature == 0.0
        assert settings.debug is False

    def test_blank_rate_limits_fall_back_too(self):
        settings = Settings(analysis_rate_limit_per_hour="", listing_parse_rate_limit_per_day="")  # type: ignore[arg-type]
        assert settings.analysis_rate_limit_per_hour == 10
        assert settings.listing_parse_rate_limit_per_day == 20

    def test_a_blank_string_variable_still_falls_back(self):
        assert Settings(ors_api_key="").ors_api_key == ""

    def test_a_real_value_is_still_honoured(self):
        assert Settings(llm_seed="42").llm_seed == 42  # type: ignore[arg-type]

    def test_genuinely_invalid_values_are_still_rejected(self):
        """Blank means unset; nonsense still means nonsense."""
        with pytest.raises(ValidationError):
            Settings(llm_seed="not-a-number")  # type: ignore[arg-type]
