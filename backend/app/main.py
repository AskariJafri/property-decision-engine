"""Application entry point.

Routes arrive in Phase F. What exists now is the app, the versioned router, and
health — enough for CI to prove the wiring holds while the engines are built.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.engines.scoring.contracts import SCORING_MODEL_VERSION

api_v1 = APIRouter(prefix="/api/v1")


@api_v1.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.environment,
        "pilot_jurisdiction": settings.pilot_jurisdiction,
        "scoring_model_version": SCORING_MODEL_VERSION,
    }


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(
        title="AI Property Decision Engine",
        version="0.1.0",
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        debug=settings.debug,
    )
    app.include_router(api_v1)
    return app


app = create_app()
