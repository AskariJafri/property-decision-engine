"""Sessions, usage, billing, watches, settings and the operational record.

The monetisation layer's tables. Three rules shape them:

* **Credits are a ledger, not a counter.** ``usage_events`` is append-only and the
  remaining allowance is derived from it, so a race or a replayed request cannot
  quietly reset a number, and every consumed analysis traces to a row.
* **Money arrives only through a verified provider event.** ``payments`` and
  ``subscriptions`` are written by the signed webhook handler and by nothing the
  browser can call. ``webhook_events`` makes that handler idempotent.
* **Nothing here holds a household's figures.** Analytics, API usage and errors
  record that something happened, never the income or price involved.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, money, uuid_fk, uuid_pk

#: JSONB on Postgres, plain JSON elsewhere — the service tests run on SQLite.
PortableJSON = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


def created_at() -> Any:
    return mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Session(Base):
    """A signed-in browser. Only a hash of the token is stored."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    """sha256 of the cookie value. A database leak yields no usable session."""

    user_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="CASCADE")
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64))


class AuthAttempt(Base):
    """Throttling for sign-up and sign-in, keyed by a hash — never the raw email or IP."""

    __tablename__ = "auth_attempts"

    id: Mapped[uuid.UUID] = uuid_pk()
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    at: Mapped[datetime] = created_at()


class UsageEvent(Base):
    """The credit ledger. One row per metered action; append-only."""

    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="CASCADE")
    analysis_id: Mapped[uuid.UUID | None] = uuid_fk(
        "property_analyses.id", nullable=True, ondelete="SET NULL"
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    """analysis, offer_scenarios, watch_recalculation, listing_parse, ..."""

    credit_source: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    """free, plan, promo, unlimited or none. Only ``free`` and ``promo`` draw down
    the free allowance."""

    credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    at: Mapped[datetime] = created_at()

    __table_args__ = (Index("ix_usage_events_user_kind_at", "user_id", "kind", "at"),)


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="CASCADE")
    product_key: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    """Mirrors the provider: active, trialing, past_due, canceled, incomplete, unpaid."""

    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_customer_id: Mapped[str | None] = mapped_column(String(255))
    provider_subscription_id: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_cents = money()
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CAD")
    interval: Mapped[str] = mapped_column(String(8), nullable=False, default="month")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("provider", "provider_subscription_id", name="uq_subscription_ref"),
    )


class Payment(Base):
    """Money actually received, as reported by the provider's signed event."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="CASCADE")
    product_key: Mapped[str] = mapped_column(String(32), nullable=False)
    analysis_id: Mapped[uuid.UUID | None] = uuid_fk(
        "property_analyses.id", nullable=True, ondelete="SET NULL"
    )
    subscription_id: Mapped[uuid.UUID | None] = uuid_fk(
        "subscriptions.id", nullable=True, ondelete="SET NULL"
    )
    amount_cents = money()
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CAD")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    fee_cents = money(nullable=True)
    fee_is_estimate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    """False only when the fee was read from the provider's balance transaction."""

    created_at: Mapped[datetime] = created_at()

    __table_args__ = (UniqueConstraint("provider", "provider_ref", name="uq_payment_ref"),)


class Report(Base):
    """An unlocked Deep Dive: which analysis, and what paid for it."""

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="CASCADE")
    analysis_id: Mapped[uuid.UUID] = uuid_fk("property_analyses.id", ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="deep_dive")
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    """purchase, plan or admin."""

    payment_id: Mapped[uuid.UUID | None] = uuid_fk(
        "payments.id", nullable=True, ondelete="SET NULL"
    )
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (UniqueConstraint("user_id", "analysis_id", "kind", name="uq_report_unlock"),)


class PropertyWatch(Base, TimestampMixin):
    __tablename__ = "property_watches"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="CASCADE")
    original_analysis_id: Mapped[uuid.UUID] = uuid_fk("property_analyses.id", ondelete="CASCADE")
    current_analysis_id: Mapped[uuid.UUID] = uuid_fk("property_analyses.id", ondelete="CASCADE")
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    listing_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    last_price_cents = money()
    days_on_market: Mapped[int | None] = mapped_column(Integer)
    provider_key: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    """Where updates come from. ``manual`` today — see ``providers/watch.py``."""


class PropertyWatchEvent(Base):
    __tablename__ = "property_watch_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    watch_id: Mapped[uuid.UUID] = uuid_fk("property_watches.id", ondelete="CASCADE")
    field: Mapped[str] = mapped_column(String(32), nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(64))
    new_value: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    analysis_id: Mapped[uuid.UUID | None] = uuid_fk(
        "property_analyses.id", nullable=True, ondelete="SET NULL"
    )
    created_at: Mapped[datetime] = created_at()


class SystemSetting(Base):
    """Admin-editable configuration: pricing, ads, features, promotions, costs."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = uuid_fk("users.id", nullable=True, ondelete="SET NULL")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="CASCADE")
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    at: Mapped[datetime] = created_at()

    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_promo_redemption"),)


class ProductEvent(Base):
    """Funnel analytics. Event names and coarse labels only — never a figure."""

    __tablename__ = "product_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", nullable=True, ondelete="SET NULL")
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    properties: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON)
    at: Mapped[datetime] = created_at()

    __table_args__ = (Index("ix_product_events_name_at", "name", "at"),)


class ApiUsage(Base):
    """One external call that costs, or might cost, money."""

    __tablename__ = "api_usage"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", nullable=True, ondelete="SET NULL")
    analysis_id: Mapped[uuid.UUID | None] = uuid_fk(
        "property_analyses.id", nullable=True, ondelete="SET NULL"
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_millicents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    """Thousandths of a cent, because one model call can cost a fraction of a cent.
    From the admin's cost assumptions, so always an estimate and labelled one. An
    integer, like every other money column (DATABASE.md)."""

    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    at: Mapped[datetime] = created_at()

    __table_args__ = (Index("ix_api_usage_at", "at"),)


class ErrorEvent(Base):
    """An unhandled server error. Path and class, never the request body."""

    __tablename__ = "error_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    error_class: Mapped[str] = mapped_column(String(128), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    at: Mapped[datetime] = created_at()


class WebhookEvent(Base):
    """Provider events already processed, so a redelivery changes nothing."""

    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[datetime] = created_at()
