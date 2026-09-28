"""A real application over a throwaway database, for the API tests.

SQLite in memory rather than Postgres, so the suite needs nothing running. Two
shims make the Postgres-shaped schema fit: JSONB compiles as JSON, and the three
tables with PostGIS geography columns (not used by any API path yet) are left
out. The migration and the Postgres-only constraints are covered separately by
``tests/integration`` against a real database in CI.

Everything that touches the database runs inside the TestClient's own event loop
(``client.portal``), because an async connection belongs to the loop that opened it.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db import session as db_session
from app.main import create_app
from app.models import Base
from app.models.user import User

GEOGRAPHY_TABLES = {"properties", "locations", "comparables"}

_emails = itertools.count(1)


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
    return "JSON"


class Api:
    """A TestClient that knows how to sign in and reach the database."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)

    def run(self, fn: Any, *args: Any) -> Any:
        return self.client.portal.call(fn, *args)  # type: ignore[union-attr]

    def signup(self, email: str | None = None, password: str = "correct horse battery") -> dict:
        email = email or f"user{next(_emails)}@example.com"
        response = self.client.post(
            "/api/v1/auth/signup", json={"email": email, "password": password}
        )
        assert response.status_code == 200, response.text
        self.client.headers["X-CSRF-Token"] = self.client.cookies["pde_csrf"]
        return response.json()

    def login(self, email: str, password: str = "correct horse battery") -> Any:
        response = self.client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        if response.status_code == 200:
            self.client.headers["X-CSRF-Token"] = self.client.cookies["pde_csrf"]
        return response

    def logout(self) -> None:
        self.client.post("/api/v1/auth/logout")
        self.client.cookies.clear()
        self.client.headers.pop("X-CSRF-Token", None)

    def set_role(self, email: str, role: str) -> None:
        async def _set() -> None:
            async with db_session.sessionmaker()() as db:
                await db.execute(update(User).where(User.email == email).values(role=role))
                await db.commit()

        self.run(_set)


@pytest.fixture
def api() -> Iterator[Api]:
    """A fresh application and empty database for each test."""
    get_settings.cache_clear()
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    db_session.configure(engine)
    tables = [t for name, t in Base.metadata.tables.items() if name not in GEOGRAPHY_TABLES]

    async def create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))

    async def dispose() -> None:
        await engine.dispose()

    with TestClient(create_app()) as client:
        client.portal.call(create)  # type: ignore[union-attr]
        yield Api(client)
        client.portal.call(dispose)  # type: ignore[union-attr]
    db_session._engine = None
    db_session._sessionmaker = None


@pytest.fixture
def client(api: Api) -> Api:
    """A signed-in ordinary user."""
    api.signup()
    return api


@pytest.fixture
def admin(api: Api) -> Api:
    """A signed-in admin, promoted directly in the database as the CLI would."""
    body = api.signup()
    api.set_role(body["user"]["email"], "admin")
    return api
