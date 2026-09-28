"""The async engine and the per-request session.

Created lazily, on first use, so importing the application — which the health
check, the reference endpoints and every pure unit test do — never opens a
connection or needs a driver to be reachable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def configure(engine: AsyncEngine) -> None:
    """Point the application at an engine. Tests use this to install SQLite."""
    global _engine, _sessionmaker
    _engine = engine
    _sessionmaker = async_sessionmaker(engine, expire_on_commit=False)


def get_engine() -> AsyncEngine:
    if _engine is None:
        settings = get_settings()
        # NullPool: a serverless function freezes between requests, and a pooled
        # connection that outlives the freeze comes back dead. One connection per
        # request is the honest shape for that host; a pooler (Neon's, PgBouncer)
        # sits in front in production.
        configure(create_async_engine(settings.database_url, poolclass=NullPool))
    assert _engine is not None
    return _engine


def sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with sessionmaker()() as session:
        yield session
