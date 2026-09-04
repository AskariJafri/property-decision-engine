"""Settings. Everything from the environment; nothing secret in the repo."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PDE_", extra="ignore")

    environment: Literal["local", "ci", "staging", "production"] = "local"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://pde:pde@localhost:5432/pde"

    # The self-hosted OSM stack (ADR 0002). Empty means "not running", and the
    # adapters degrade to UNAVAILABLE rather than failing an analysis.
    nominatim_url: str = ""
    routing_url: str = ""
    overpass_url: str = ""

    # Pilot jurisdiction (ADR 0003). A setting rather than a constant because the
    # second city is a configuration change, not a rewrite.
    pilot_jurisdiction: str = "ON/Toronto"

    session_secret: str = "dev-only-not-a-secret"
    analysis_rate_limit_per_hour: int = 10
    listing_parse_rate_limit_per_day: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
