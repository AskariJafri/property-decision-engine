"""Application entry point."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.admin import router as admin_router
from app.api.v1.analyses import router as analyses_router
from app.api.v1.auth import router as auth_router
from app.api.v1.billing import router as billing_router
from app.api.v1.routes import router as api_v1
from app.api.v1.watch import router as watch_router
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
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
    )
    for router in (
        api_v1,
        auth_router,
        analyses_router,
        watch_router,
        billing_router,
        admin_router,
    ):
        app.include_router(router)

    @app.middleware("http")
    async def limit_body_size(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Refuse an oversized body before anything reads it.

        The declared length is checked here; uploads are additionally read with a
        hard cap in the handler, since a client can lie about the length.
        """
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > settings.max_request_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": "That request is too large. Files are limited to 5 MB."},
            )
        return await call_next(request)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        """Record the failure for the admin console — path and class, never the body."""
        logging.getLogger(__name__).exception("Unhandled error on %s", request.url.path)
        try:
            from app.db.session import sessionmaker
            from app.models.account import ErrorEvent

            async with sessionmaker()() as db:
                db.add(
                    ErrorEvent(
                        method=request.method[:8],
                        path=request.url.path[:255],
                        error_class=type(exc).__name__[:128],
                        message=str(exc)[:500],
                    )
                )
                await db.commit()
        except Exception:  # recording an error must never raise another
            logging.getLogger(__name__).warning("Could not record the error event.")
        return JSONResponse(
            status_code=500, content={"detail": "Something went wrong on our side."}
        )

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
