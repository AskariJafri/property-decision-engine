"""Settings. Everything from the environment; nothing secret in the repo."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Both locations, repo root first so a backend/.env can override it. The API
    # runs from backend/, and looking only there meant a .env sitting next to
    # .env.example at the root was silently ignored.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_prefix="PDE_", extra="ignore"
    )

    environment: Literal["local", "ci", "staging", "production"] = "local"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://pde:pde@localhost:5432/pde"

    # The self-hosted OSM stack (ADR 0002). Empty means "not running", and the
    # adapters degrade to UNAVAILABLE rather than failing an analysis.
    nominatim_url: str = ""
    routing_url: str = ""
    overpass_url: str = ""

    # OpenRouteService: the free-tier stopgap that makes the Location score real
    # before the self-hosted OSM box exists (ADR 0002). Blank means no location
    # data at all, which the analysis reports rather than guesses around.
    ors_api_key: str = ""
    ors_base_url: str = "https://api.openrouteservice.org"

    # Local model first (ADR 0004). Ollama speaks the OpenAI-compatible shape, so
    # moving to a free hosted tier later is a base-URL and model-name change. Blank
    # base URL means no model: judgements come back unavailable and the analysis
    # degrades, exactly as it does when any other provider is down.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "llama3.1:8b-instruct-q4_K_M"
    """The exact tag. An alias like "llama3" would silently change under us and
    break the pinning that makes judgements replayable."""

    llm_api_key: str = ""
    """Sent as a bearer token when set. Ollama needs none; every hosted tier does."""

    llm_temperature: float = 0.0
    llm_seed: int = 7
    llm_timeout_seconds: float = 90.0
    llm_max_tokens: int = 1024

    # Off unless asked for, and the default base URL is why. It points at
    # localhost, which on a serverless host is the function's own container: a
    # request there does not fail fast, it hangs until the timeout and takes the
    # whole analysis down with it. An explicit flag means a deployment cannot
    # start paying that cost by accident, and it keeps "a model is configured"
    # from being mistaken for "explanations are on" the way the old health flag
    # was. Turn it on where a model is genuinely reachable.
    llm_explanations_enabled: bool = False

    # Deliberately short, and separate from llm_timeout_seconds. Generation can
    # reasonably take a minute; discovering that nothing is listening should take
    # a moment. Without this split, a wrong base URL costs every request the full
    # generation timeout before degrading.
    llm_connect_timeout_seconds: float = 3.0

    # Pilot jurisdiction (ADR 0003). A setting rather than a constant because the
    # second city is a configuration change, not a rewrite.
    pilot_jurisdiction: str = "ON/Toronto"

    # The browser sends a preflight before any cross-origin POST, so the API has
    # to name the origins it will answer. Explicit list, never a wildcard: this
    # endpoint receives a household's income and debts.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    session_secret: str = "dev-only-not-a-secret"
    analysis_rate_limit_per_hour: int = 10
    listing_parse_rate_limit_per_day: int = 20

    @model_validator(mode="before")
    @classmethod
    def blank_means_unset(cls, data: Any) -> Any:
        """Treat an empty environment variable as absent, so the default applies.

        Deployment platforms make blank values trivially easy to create — an
        imported .env template, a key added before its value is known, a copied
        row. Pydantic reads "" as a value and rejects it for anything that is not
        a string, so a blank PDE_LLM_SEED took down the entire application at
        import with five validation errors and a 500 that says nothing about
        which variable is at fault.

        A variable that is present but empty is one nobody has set yet. Dropping
        it here is the difference between a working deployment and an outage.
        """
        if isinstance(data, dict):
            return {
                key: value
                for key, value in data.items()
                if not (isinstance(value, str) and not value.strip())
            }
        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()
