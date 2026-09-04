"""The provenance spine: sources, facts, and the dated rule registry.

Three CHECK constraints in this module carry more of the product's promise than
any amount of application code:

* an ``unavailable`` fact must state why it is unavailable;
* an ``unverified`` rule cannot be active;
* a ``prohibited`` source cannot be marked storable.

Each is a claim the product makes to its users, expressed where it cannot be
forgotten, refactored away, or bypassed by a script.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_fk, uuid_pk

SOURCE_CLASSES = (
    "verified",
    "calculated",
    "estimated",
    "assumed",
    "ai_inferred",
    "user_asserted",
    "unavailable",
)
LICENCE_CLASSES = ("open", "licensed", "restricted", "prohibited")
VERIFICATIONS = ("primary", "secondary", "unverified")


class DataSource(Base, TimestampMixin):
    """One row per provider, carrying its licence terms.

    The ``prohibited`` rows exist on purpose. REALTOR.ca and the listing portals
    are recorded here so that attaching a fact to them fails a constraint rather
    than being a question someone raises in code review.
    """

    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    licence_class: Mapped[str] = mapped_column(
        Enum(*LICENCE_CLASSES, name="licence_class"), nullable=False
    )
    may_store_values: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_retention_days: Mapped[int | None] = mapped_column(Integer)
    attribution_text: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    terms_url: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        CheckConstraint(
            "NOT (licence_class = 'prohibited' AND may_store_values)",
            name="prohibited_is_never_storable",
        ),
        CheckConstraint(
            "max_retention_days IS NULL OR max_retention_days > 0",
            name="retention_is_positive",
        ),
    )


class DataProvenance(Base):
    """The audit record for one externally sourced or derived fact."""

    __tablename__ = "data_provenance"

    id: Mapped[uuid.UUID] = uuid_pk()
    data_source_id: Mapped[uuid.UUID] = uuid_fk("data_sources.id")
    source_class: Mapped[str] = mapped_column(
        Enum(*SOURCE_CLASSES, name="source_class"), nullable=False
    )
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """When the value was *true*: the by-law year, the assessment year, the sale date."""

    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unavailable_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "source_class <> 'unavailable' OR unavailable_reason IS NOT NULL",
            name="unavailable_states_why",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_is_a_fraction"),
        Index(
            "ix_data_provenance_expiring",
            "expires_at",
            postgresql_where=text("expires_at IS NOT NULL"),
        ),
    )


class Rule(Base, TimestampMixin):
    """A dated, sourced rule. Toronto's April 2026 luxury bands are why this exists."""

    __tablename__ = "rules"

    id: Mapped[uuid.UUID] = uuid_pk()
    jurisdiction: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    verification: Mapped[str] = mapped_column(
        Enum(*VERIFICATIONS, name="rule_verification"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("jurisdiction", "name", "version", name="uq_rules_jurisdiction_name_ver"),
        CheckConstraint(
            "NOT (verification = 'unverified' AND active)",
            name="unverified_is_never_active",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="effective_range_is_ordered",
        ),
        Index(
            "ix_rules_lookup",
            "jurisdiction",
            "name",
            "effective_from",
            postgresql_where=text("active"),
        ),
    )


class RuleSet(Base):
    """An immutable snapshot, stamped onto every analysis so a replay is exact."""

    __tablename__ = "rule_sets"

    id: Mapped[uuid.UUID] = uuid_pk()
    label: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rule_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class MarketSnapshot(Base):
    """Market context is dated data, never a constant in code."""

    __tablename__ = "market_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    jurisdiction: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    publisher: Mapped[str] = mapped_column(String(128), nullable=False)
    provenance_id: Mapped[uuid.UUID] = uuid_fk("data_provenance.id")

    __table_args__ = (
        UniqueConstraint("jurisdiction", "as_of", "metric", name="uq_market_snapshot_point"),
    )
