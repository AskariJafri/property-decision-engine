"""Identity, financial profile and buyer preferences.

The financial profile is versioned rather than updated. An analysis references the
profile row it was computed against, so raising your income next March does not
retroactively change what last September's analysis said — which is the difference
between a record and a number that drifts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, encrypted, uuid_fk, uuid_pk

CREDIT_BANDS = ("under_600", "600_659", "660_719", "720_plus", "unknown")
RESIDENCY = ("citizen_or_pr", "foreign_national", "unknown")
HORIZONS = ("under_3", "3_to_5", "5_to_10", "over_10")
GOALS = ("primary_residence", "investment", "house_hack", "mixed")
RISK_POSTURES = ("conservative", "balanced", "aggressive")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Set on a deletion request. A worker hard-deletes after the grace window —
    PIPEDA deletion has to actually delete, so this is a queue, not a tombstone."""


class UserProfile(Base, TimestampMixin):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="CASCADE")
    display_name: Mapped[str | None] = mapped_column(String(200))
    locale: Mapped[str] = mapped_column(String(10), default="en-CA", nullable=False)
    home_jurisdiction: Mapped[str] = mapped_column(String(64), default="ON/Toronto", nullable=False)


class FinancialProfile(Base, TimestampMixin):
    """Sensitive. Every money column is opaque bytes at rest.

    ``valid_from``/``valid_to`` make this an append-only history: a change closes
    the current row and opens a new one, so an analysis can be replayed against
    the profile exactly as it stood when it ran.
    """

    __tablename__ = "financial_profiles"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="CASCADE")

    gross_annual_income_cents = encrypted()
    household_income_cents = encrypted()
    monthly_debt_payments_cents = encrypted()
    down_payment_cents = encrypted()
    available_savings_cents = encrypted()
    emergency_fund_cents = encrypted()
    fhsa_balance_cents = encrypted()
    rrsp_hbp_available_cents = encrypted()
    desired_max_monthly_cents = encrypted()

    first_time_buyer: Mapped[bool | None] = mapped_column(Boolean)
    credit_score_band: Mapped[str] = mapped_column(
        Enum(*CREDIT_BANDS, name="credit_score_band"), default="unknown", nullable=False
    )
    residency_status: Mapped[str] = mapped_column(
        Enum(*RESIDENCY, name="residency_status"), default="unknown", nullable=False
    )
    """Never assumed: getting this wrong omits a 25% provincial tax, or invents one."""

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BuyerPreferences(Base, TimestampMixin):
    __tablename__ = "buyer_preferences"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="CASCADE")

    min_bedrooms: Mapped[int | None] = mapped_column(Integer)
    min_bathrooms: Mapped[int | None] = mapped_column(Integer)
    property_types: Mapped[list[str] | None] = mapped_column(JSONB)
    requires_parking: Mapped[bool | None] = mapped_column(Boolean)
    requires_garage: Mapped[bool | None] = mapped_column(Boolean)
    requires_basement: Mapped[bool | None] = mapped_column(Boolean)
    requires_yard: Mapped[bool | None] = mapped_column(Boolean)

    # A point-to-point commute needs coordinates, not geometry — PostGIS earns its
    # place on the property side, where the risk engine intersects flood polygons.
    work_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    work_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    max_commute_minutes: Mapped[int | None] = mapped_column(Integer)
    commute_mode: Mapped[str | None] = mapped_column(String(20))

    household_size: Mapped[int | None] = mapped_column(Integer)
    has_children: Mapped[bool | None] = mapped_column(Boolean)

    # 0-5 importance dials, which become the weight modifiers in SCORING_MODEL.md §2.
    schools_importance: Mapped[int | None] = mapped_column(Integer)
    walkability_importance: Mapped[int | None] = mapped_column(Integer)
    quiet_importance: Mapped[int | None] = mapped_column(Integer)
    resale_importance: Mapped[int | None] = mapped_column(Integer)
    transit_importance: Mapped[int | None] = mapped_column(Integer)

    time_horizon: Mapped[str | None] = mapped_column(Enum(*HORIZONS, name="time_horizon"))
    goal: Mapped[str | None] = mapped_column(Enum(*GOALS, name="buyer_goal"))
    risk_posture: Mapped[str | None] = mapped_column(Enum(*RISK_POSTURES, name="risk_posture"))

    free_text_wants: Mapped[str | None] = mapped_column(Text)
    """What no checkbox captures. Parsed into structure by a preference_interpretation
    judgement (ADR 0004), which becomes USER_ASSERTED once the user confirms it."""

    weight_overrides: Mapped[dict[str, float] | None] = mapped_column(JSONB)

    __table_args__ = (UniqueConstraint("user_id", name="uq_buyer_preferences_user_id"),)


class AuditLog(Base):
    """Who touched a financial profile. The fact of access, never the values."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    actor_user_id: Mapped[uuid.UUID | None] = uuid_fk("users.id", nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
