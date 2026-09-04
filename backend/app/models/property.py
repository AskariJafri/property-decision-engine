"""Property, its attributes, and location.

``property_attributes`` holds **one row per field per source**, which is the
difference between provenance as a feature and provenance as a comment. When the
user says 1,450 sq ft and the municipal footprint implies 1,380, both rows exist,
the conflict is visible, and no code silently picks a winner — resolution is a
documented function over the rows, not a column someone overwrites.

Coordinates are stored as PostGIS geography because the risk engine intersects
them with TRCA flood polygons, and because the self-hosted ODbL stack lets us
store them permanently (ADR 0002 §1).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, money, uuid_fk, uuid_pk

PROPERTY_KINDS = (
    "detached",
    "semi",
    "townhouse",
    "condo_apartment",
    "condo_town",
    "duplex",
    "other",
)
SOURCE_TYPES = ("manual", "pasted_text", "pdf", "screenshot")
PRICE_EVENTS = ("listed", "reduced", "increased", "relisted", "sold")


class Property(Base, TimestampMixin):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_by_user_id: Mapped[uuid.UUID] = uuid_fk("users.id")

    address_normalized: Mapped[str] = mapped_column(String(400), nullable=False)
    street: Mapped[str | None] = mapped_column(String(200))
    unit: Mapped[str | None] = mapped_column(String(32))
    city: Mapped[str | None] = mapped_column(String(120))
    province: Mapped[str] = mapped_column(String(2), default="ON", nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(10))

    geom: Mapped[object | None] = mapped_column(Geography("POINT", srid=4326, spatial_index=False))
    geocode_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    osm_feature_id: Mapped[str | None] = mapped_column(String(64))

    jurisdiction: Mapped[str] = mapped_column(String(64), nullable=False)
    """``ON/Toronto``. The rule-registry lookup key, and what decides whether
    municipal land transfer tax resolves at all."""

    property_kind: Mapped[str | None] = mapped_column(Enum(*PROPERTY_KINDS, name="property_kind"))
    listing_price_cents = money(nullable=True)

    __table_args__ = (
        UniqueConstraint("address_normalized", "unit", name="uq_properties_address_unit"),
        Index("ix_properties_geom", "geom", postgresql_using="gist"),
    )


class PropertySource(Base, TimestampMixin):
    """One ingestion event.

    ``source_url`` is recorded when the user supplies one and is **never fetched**
    (ADR 0002 §2). It exists so the user can see where their own information came
    from, not so we can go and get more of it.
    """

    __tablename__ = "property_sources"

    id: Mapped[uuid.UUID] = uuid_pk()
    property_id: Mapped[uuid.UUID] = uuid_fk("properties.id", ondelete="CASCADE")
    source_type: Mapped[str] = mapped_column(
        Enum(*SOURCE_TYPES, name="property_source_type"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_payload_ref: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by_user_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Nothing extracted becomes an attribute until this is set."""


class PropertyAttribute(Base, TimestampMixin):
    """One field, from one source. Corrections supersede rather than overwrite."""

    __tablename__ = "property_attributes"

    id: Mapped[uuid.UUID] = uuid_pk()
    property_id: Mapped[uuid.UUID] = uuid_fk("properties.id", ondelete="CASCADE")
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    provenance_id: Mapped[uuid.UUID] = uuid_fk("data_provenance.id")
    superseded_by: Mapped[uuid.UUID | None] = uuid_fk("property_attributes.id", nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "property_id", "field", "provenance_id", name="uq_property_attribute_source"
        ),
        Index("ix_property_attributes_field", "property_id", "field"),
    )


class PropertyPriceHistory(Base):
    __tablename__ = "property_price_history"

    id: Mapped[uuid.UUID] = uuid_pk()
    property_id: Mapped[uuid.UUID] = uuid_fk("properties.id", ondelete="CASCADE")
    price_cents = money()
    event: Mapped[str] = mapped_column(Enum(*PRICE_EVENTS, name="price_event"), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    provenance_id: Mapped[uuid.UUID] = uuid_fk("data_provenance.id")


class Location(Base, TimestampMixin):
    """A geocoded point we have enriched, plus our own derived metrics."""

    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = uuid_pk()
    geom: Mapped[object] = mapped_column(
        Geography("POINT", srid=4326, spatial_index=False), nullable=False
    )
    osm_feature_id: Mapped[str | None] = mapped_column(String(64))
    jurisdiction: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (Index("ix_locations_geom", "geom", postgresql_using="gist"),)


class LocationMetric(Base):
    __tablename__ = "location_metrics"

    id: Mapped[uuid.UUID] = uuid_pk()
    location_id: Mapped[uuid.UUID] = uuid_fk("locations.id", ondelete="CASCADE")
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(16))
    provenance_id: Mapped[uuid.UUID] = uuid_fk("data_provenance.id")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Nothing in the free stack sets this. The column and its sweeper stay so that
    a future retention-capped provider cannot be wired in without honouring it."""


class SavedProperty(Base, TimestampMixin):
    __tablename__ = "saved_properties"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="CASCADE")
    property_id: Mapped[uuid.UUID] = uuid_fk("properties.id", ondelete="CASCADE")
    note: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "property_id", name="uq_saved_property"),)


class Comparable(Base, TimestampMixin):
    """A sold property the user supplied.

    ``owner_user_id`` is NOT NULL, and that is the schema refusing to allow a
    shared pool. Comps come from the person entitled to see them, and pooling
    MLS-derived figures across users would recreate the licensing problem by
    another route (DATA_LICENSING.md §3.6).
    """

    __tablename__ = "comparables"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="CASCADE")
    address: Mapped[str] = mapped_column(String(400), nullable=False)
    geom: Mapped[object | None] = mapped_column(Geography("POINT", srid=4326, spatial_index=False))
    sale_price_cents = money()
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    attributes: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    property_kind: Mapped[str | None] = mapped_column(Enum(*PROPERTY_KINDS, name="comp_kind"))
    provenance_id: Mapped[uuid.UUID] = uuid_fk("data_provenance.id")

    __table_args__ = (Index("ix_comparables_geom", "geom", postgresql_using="gist"),)
