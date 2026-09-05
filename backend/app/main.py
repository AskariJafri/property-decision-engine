"""Application entry point."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
    )
    app.include_router(api_v1)

    @app.exception_handler(404)
    async def not_found(request: Request, exc: object) -> JSONResponse:
        """Say which path was received, not just that it was not found.

        Behind a proxy or a platform rewrite, the path the application sees is
        often not the path the client asked for — and a bare "Not Found" hides
        exactly the fact needed to diagnose that. This cost a deploy cycle to
        work out once.
        """
        return JSONResponse(
            status_code=404,
            content={
                "detail": "Not Found",
                "path_received": request.url.path,
                "hint": "The API is served under /api/v1. Try /api/v1/health.",
            },
        )

    return app


app = create_app()
