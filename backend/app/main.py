"""Application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.routes import router as api_v1
from app.core.config import get_settings
from app.core.logging import configure_logging


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
