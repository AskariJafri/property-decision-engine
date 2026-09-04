"""Declarative base, shared column types, and the conventions DATABASE.md promises.

Two of those conventions are load-bearing enough to be types rather than habits:

``money`` is ``BigInteger`` and every column using it ends ``_cents``. There is no
helper that takes a float, so a float cannot enter a financial column by accident.

``EncryptedBytes`` marks the columns holding a household's income, debts and
savings. The ciphering itself belongs to the profile service (Phase F); what the
schema fixes now is that these are opaque bytes at rest, so a stray ``SELECT *``
in a log or a database dump yields nothing readable.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, LargeBinary, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Named constraints throughout, so a migration can drop one by name."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def uuid_fk(target: str, *, nullable: bool = False, ondelete: str | None = None) -> Any:
    from sqlalchemy import ForeignKey

    return mapped_column(
        PGUUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True
    )


def money(*, nullable: bool = False, default: int | None = None) -> Any:
    """A monetary column. Integer cents, never a float, name ends ``_cents``."""
    return mapped_column(BigInteger, nullable=nullable, default=default)


def encrypted() -> Any:
    """Opaque at rest. The service layer holds the key; the database never sees a value."""
    return mapped_column(LargeBinary, nullable=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
