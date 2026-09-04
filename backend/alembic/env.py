"""Alembic environment.

The URL comes from settings, never from alembic.ini, so migrations run against
whatever the application is configured for and there is no second place to keep a
connection string in sync.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import get_settings
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Autogenerate manages only the tables we declare.

    The PostGIS image ships the TIGER geocoder — ``tract``, ``addrfeat``,
    ``zip_state`` and a few dozen more — plus ``spatial_ref_sys``. Left alone,
    autogenerate cheerfully proposes ``DROP TABLE`` for every one of them, and
    that is precisely the diff that gets rubber-stamped once and takes a database
    with it.

    So a reflected table we did not declare is not ours to touch. The trade-off is
    that deleting a model no longer auto-generates its ``DROP TABLE``; that has to
    be written by hand, which is the right amount of friction for a destructive
    change.
    """
    if type_ == "table" and reflected and name not in target_metadata.tables:
        return False
    return not (type_ == "index" and reflected and name is not None and name.startswith("idx_"))


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
