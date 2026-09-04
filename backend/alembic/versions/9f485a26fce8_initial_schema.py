"""initial schema

Identity, property, provenance and analysis, per docs/DATABASE.md.

The constraints matter as much as the columns: an unavailable fact must state
why, an unverified rule cannot be active, a prohibited source cannot be marked
storable, a withheld Buy Score must explain itself, and an AI judgement can only
ever raise a POTENTIAL risk flag. Those are product promises expressed where they
cannot be forgotten.

Revision ID: 9f485a26fce8
Revises:
Create Date: 2026-09-04 02:34:45.215039

"""

from typing import Sequence, Union

from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9f485a26fce8"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Geography columns need the extension before any table that uses one. The CI
    # service and docker-compose both run the postgis image, so this is a no-op
    # there and a clear failure anywhere PostGIS is genuinely missing.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "data_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "licence_class",
            sa.Enum("open", "licensed", "restricted", "prohibited", name="licence_class"),
            nullable=False,
        ),
        sa.Column("may_store_values", sa.Boolean(), nullable=False),
        sa.Column("max_retention_days", sa.Integer(), nullable=True),
        sa.Column("attribution_text", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("terms_url", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "NOT (licence_class = 'prohibited' AND may_store_values)",
            name=op.f("ck_data_sources_prohibited_is_never_storable"),
        ),
        sa.CheckConstraint(
            "max_retention_days IS NULL OR max_retention_days > 0",
            name=op.f("ck_data_sources_retention_is_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_sources")),
        sa.UniqueConstraint("key", name=op.f("uq_data_sources_key")),
    )
    op.create_table(
        "locations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeogFromText",
                name="geography",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("osm_feature_id", sa.String(length=64), nullable=True),
        sa.Column("jurisdiction", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locations")),
    )
    op.create_index(
        "ix_locations_geom", "locations", ["geom"], unique=False, postgresql_using="gist"
    )
    op.create_table(
        "rule_sets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=32), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rule_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_sets")),
        sa.UniqueConstraint("label", name=op.f("uq_rule_sets_label")),
    )
    op.create_table(
        "rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("jurisdiction", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column(
            "verification",
            sa.Enum("primary", "secondary", "unverified", name="rule_verification"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "NOT (verification = 'unverified' AND active)",
            name=op.f("ck_rules_unverified_is_never_active"),
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name=op.f("ck_rules_effective_range_is_ordered"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rules")),
        sa.UniqueConstraint(
            "jurisdiction", "name", "version", name="uq_rules_jurisdiction_name_ver"
        ),
    )
    op.create_index(
        "ix_rules_lookup",
        "rules",
        ["jurisdiction", "name", "effective_from"],
        unique=False,
        postgresql_where=sa.text("active"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name=op.f("fk_audit_logs_actor_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        op.f("ix_audit_logs_actor_user_id"), "audit_logs", ["actor_user_id"], unique=False
    )
    op.create_table(
        "buyer_preferences",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("min_bedrooms", sa.Integer(), nullable=True),
        sa.Column("min_bathrooms", sa.Integer(), nullable=True),
        sa.Column("property_types", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("requires_parking", sa.Boolean(), nullable=True),
        sa.Column("requires_garage", sa.Boolean(), nullable=True),
        sa.Column("requires_basement", sa.Boolean(), nullable=True),
        sa.Column("requires_yard", sa.Boolean(), nullable=True),
        sa.Column("work_latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("work_longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("max_commute_minutes", sa.Integer(), nullable=True),
        sa.Column("commute_mode", sa.String(length=20), nullable=True),
        sa.Column("household_size", sa.Integer(), nullable=True),
        sa.Column("has_children", sa.Boolean(), nullable=True),
        sa.Column("schools_importance", sa.Integer(), nullable=True),
        sa.Column("walkability_importance", sa.Integer(), nullable=True),
        sa.Column("quiet_importance", sa.Integer(), nullable=True),
        sa.Column("resale_importance", sa.Integer(), nullable=True),
        sa.Column("transit_importance", sa.Integer(), nullable=True),
        sa.Column(
            "time_horizon",
            sa.Enum("under_3", "3_to_5", "5_to_10", "over_10", name="time_horizon"),
            nullable=True,
        ),
        sa.Column(
            "goal",
            sa.Enum("primary_residence", "investment", "house_hack", "mixed", name="buyer_goal"),
            nullable=True,
        ),
        sa.Column(
            "risk_posture",
            sa.Enum("conservative", "balanced", "aggressive", name="risk_posture"),
            nullable=True,
        ),
        sa.Column("free_text_wants", sa.Text(), nullable=True),
        sa.Column("weight_overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_buyer_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_buyer_preferences")),
        sa.UniqueConstraint("user_id", name="uq_buyer_preferences_user_id"),
    )
    op.create_index(
        op.f("ix_buyer_preferences_user_id"), "buyer_preferences", ["user_id"], unique=False
    )
    op.create_table(
        "data_provenance",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("data_source_id", sa.UUID(), nullable=False),
        sa.Column(
            "source_class",
            sa.Enum(
                "verified",
                "calculated",
                "estimated",
                "assumed",
                "ai_inferred",
                "user_asserted",
                "unavailable",
                name="source_class",
            ),
            nullable=False,
        ),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unavailable_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "source_class <> 'unavailable' OR unavailable_reason IS NOT NULL",
            name=op.f("ck_data_provenance_unavailable_states_why"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_data_provenance_confidence_is_a_fraction"),
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["data_sources.id"],
            name=op.f("fk_data_provenance_data_source_id_data_sources"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_provenance")),
    )
    op.create_index(
        op.f("ix_data_provenance_data_source_id"),
        "data_provenance",
        ["data_source_id"],
        unique=False,
    )
    op.create_index(
        "ix_data_provenance_expiring",
        "data_provenance",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )
    op.create_table(
        "financial_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("gross_annual_income_cents", sa.LargeBinary(), nullable=True),
        sa.Column("household_income_cents", sa.LargeBinary(), nullable=True),
        sa.Column("monthly_debt_payments_cents", sa.LargeBinary(), nullable=True),
        sa.Column("down_payment_cents", sa.LargeBinary(), nullable=True),
        sa.Column("available_savings_cents", sa.LargeBinary(), nullable=True),
        sa.Column("emergency_fund_cents", sa.LargeBinary(), nullable=True),
        sa.Column("fhsa_balance_cents", sa.LargeBinary(), nullable=True),
        sa.Column("rrsp_hbp_available_cents", sa.LargeBinary(), nullable=True),
        sa.Column("desired_max_monthly_cents", sa.LargeBinary(), nullable=True),
        sa.Column("first_time_buyer", sa.Boolean(), nullable=True),
        sa.Column(
            "credit_score_band",
            sa.Enum(
                "under_600", "600_659", "660_719", "720_plus", "unknown", name="credit_score_band"
            ),
            nullable=False,
        ),
        sa.Column(
            "residency_status",
            sa.Enum("citizen_or_pr", "foreign_national", "unknown", name="residency_status"),
            nullable=False,
        ),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_financial_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_profiles")),
    )
    op.create_index(
        op.f("ix_financial_profiles_user_id"), "financial_profiles", ["user_id"], unique=False
    )
    op.create_table(
        "properties",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("address_normalized", sa.String(length=400), nullable=False),
        sa.Column("street", sa.String(length=200), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("province", sa.String(length=2), nullable=False),
        sa.Column("postal_code", sa.String(length=10), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeogFromText",
                name="geography",
            ),
            nullable=True,
        ),
        sa.Column("geocode_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("osm_feature_id", sa.String(length=64), nullable=True),
        sa.Column("jurisdiction", sa.String(length=64), nullable=False),
        sa.Column(
            "property_kind",
            sa.Enum(
                "detached",
                "semi",
                "townhouse",
                "condo_apartment",
                "condo_town",
                "duplex",
                "other",
                name="property_kind",
            ),
            nullable=True,
        ),
        sa.Column("listing_price_cents", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_properties_created_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_properties")),
        sa.UniqueConstraint("address_normalized", "unit", name="uq_properties_address_unit"),
    )
    op.create_index(
        op.f("ix_properties_created_by_user_id"), "properties", ["created_by_user_id"], unique=False
    )
    op.create_index(
        "ix_properties_geom", "properties", ["geom"], unique=False, postgresql_using="gist"
    )
    op.create_table(
        "property_comparisons",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("analysis_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("verdicts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_property_comparisons_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_comparisons")),
    )
    op.create_index(
        op.f("ix_property_comparisons_user_id"), "property_comparisons", ["user_id"], unique=False
    )
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("home_jurisdiction", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_profiles")),
    )
    op.create_index(op.f("ix_user_profiles_user_id"), "user_profiles", ["user_id"], unique=False)
    op.create_table(
        "ai_judgements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column(
            "judgement_type",
            sa.Enum(
                "condition_signal",
                "listing_red_flags",
                "omission_signals",
                "preference_interpretation",
                "decision_review",
                name="ai_judgement_type",
            ),
            nullable=False,
        ),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("influence_cap", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("sampling", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("judgement_version", sa.String(length=16), nullable=False),
        sa.Column("numeric_guard_passed", sa.Boolean(), nullable=False),
        sa.Column("user_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_ai_judgements_judgement_confidence_fraction"),
        ),
        sa.CheckConstraint(
            "influence_cap >= 0", name=op.f("ck_ai_judgements_influence_cap_is_positive")
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_ai_judgements_property_id_properties"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_judgements")),
    )
    op.create_index(
        op.f("ix_ai_judgements_property_id"), "ai_judgements", ["property_id"], unique=False
    )
    op.create_index(
        "ix_ai_judgements_property_type",
        "ai_judgements",
        ["property_id", "judgement_type"],
        unique=False,
    )
    op.create_table(
        "comparables",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("address", sa.String(length=400), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeogFromText",
                name="geography",
            ),
            nullable=True,
        ),
        sa.Column("sale_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "property_kind",
            sa.Enum(
                "detached",
                "semi",
                "townhouse",
                "condo_apartment",
                "condo_town",
                "duplex",
                "other",
                name="comp_kind",
            ),
            nullable=True,
        ),
        sa.Column("provenance_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_comparables_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["data_provenance.id"],
            name=op.f("fk_comparables_provenance_id_data_provenance"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comparables")),
    )
    op.create_index(
        "ix_comparables_geom", "comparables", ["geom"], unique=False, postgresql_using="gist"
    )
    op.create_index(
        op.f("ix_comparables_owner_user_id"), "comparables", ["owner_user_id"], unique=False
    )
    op.create_index(
        op.f("ix_comparables_provenance_id"), "comparables", ["provenance_id"], unique=False
    )
    op.create_table(
        "location_metrics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("provenance_id", sa.UUID(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_location_metrics_location_id_locations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["data_provenance.id"],
            name=op.f("fk_location_metrics_provenance_id_data_provenance"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_location_metrics")),
    )
    op.create_index(
        op.f("ix_location_metrics_location_id"), "location_metrics", ["location_id"], unique=False
    )
    op.create_index(
        op.f("ix_location_metrics_provenance_id"),
        "location_metrics",
        ["provenance_id"],
        unique=False,
    )
    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("jurisdiction", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("publisher", sa.String(length=128), nullable=False),
        sa.Column("provenance_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["data_provenance.id"],
            name=op.f("fk_market_snapshots_provenance_id_data_provenance"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_snapshots")),
        sa.UniqueConstraint("jurisdiction", "as_of", "metric", name="uq_market_snapshot_point"),
    )
    op.create_index(
        op.f("ix_market_snapshots_provenance_id"),
        "market_snapshots",
        ["provenance_id"],
        unique=False,
    )
    op.create_table(
        "property_analyses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("financial_profile_id", sa.UUID(), nullable=False),
        sa.Column("buyer_preferences_id", sa.UUID(), nullable=False),
        sa.Column("rule_set_id", sa.UUID(), nullable=False),
        sa.Column("scoring_model_version", sa.String(length=16), nullable=False),
        sa.Column("buy_score", sa.SmallInteger(), nullable=True),
        sa.Column("score_withheld_reason", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("weights_applied", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("fair_value_low_cents", sa.BigInteger(), nullable=True),
        sa.Column("fair_value_high_cents", sa.BigInteger(), nullable=True),
        sa.Column("suggested_offer_low_cents", sa.BigInteger(), nullable=True),
        sa.Column("suggested_offer_high_cents", sa.BigInteger(), nullable=True),
        sa.Column("monthly_ownership_cost_cents", sa.BigInteger(), nullable=True),
        sa.Column("closing_costs_cents", sa.BigInteger(), nullable=True),
        sa.Column("cash_required_cents", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "buy_score IS NOT NULL OR score_withheld_reason IS NOT NULL",
            name=op.f("ck_property_analyses_withheld_score_states_why"),
        ),
        sa.CheckConstraint(
            "buy_score IS NULL OR (buy_score >= 0 AND buy_score <= 100)",
            name=op.f("ck_property_analyses_buy_score_in_range"),
        ),
        sa.CheckConstraint(
            "fair_value_high_cents IS NULL OR fair_value_low_cents IS NULL OR fair_value_high_cents >= fair_value_low_cents",
            name=op.f("ck_property_analyses_fair_value_is_a_range"),
        ),
        sa.ForeignKeyConstraint(
            ["buyer_preferences_id"],
            ["buyer_preferences.id"],
            name=op.f("fk_property_analyses_buyer_preferences_id_buyer_preferences"),
        ),
        sa.ForeignKeyConstraint(
            ["financial_profile_id"],
            ["financial_profiles.id"],
            name=op.f("fk_property_analyses_financial_profile_id_financial_profiles"),
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_property_analyses_property_id_properties"),
        ),
        sa.ForeignKeyConstraint(
            ["rule_set_id"],
            ["rule_sets.id"],
            name=op.f("fk_property_analyses_rule_set_id_rule_sets"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_property_analyses_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_analyses")),
    )
    op.create_index(
        op.f("ix_property_analyses_buyer_preferences_id"),
        "property_analyses",
        ["buyer_preferences_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_property_analyses_financial_profile_id"),
        "property_analyses",
        ["financial_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_property_analyses_property_id"), "property_analyses", ["property_id"], unique=False
    )
    op.create_index(
        op.f("ix_property_analyses_rule_set_id"), "property_analyses", ["rule_set_id"], unique=False
    )
    op.create_index(
        op.f("ix_property_analyses_user_id"), "property_analyses", ["user_id"], unique=False
    )
    op.create_index(
        "ix_property_analyses_user_recent",
        "property_analyses",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "property_attributes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provenance_id", sa.UUID(), nullable=False),
        sa.Column("superseded_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_property_attributes_property_id_properties"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["data_provenance.id"],
            name=op.f("fk_property_attributes_provenance_id_data_provenance"),
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by"],
            ["property_attributes.id"],
            name=op.f("fk_property_attributes_superseded_by_property_attributes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_attributes")),
        sa.UniqueConstraint(
            "property_id", "field", "provenance_id", name="uq_property_attribute_source"
        ),
    )
    op.create_index(
        "ix_property_attributes_field",
        "property_attributes",
        ["property_id", "field"],
        unique=False,
    )
    op.create_index(
        op.f("ix_property_attributes_property_id"),
        "property_attributes",
        ["property_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_property_attributes_provenance_id"),
        "property_attributes",
        ["provenance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_property_attributes_superseded_by"),
        "property_attributes",
        ["superseded_by"],
        unique=False,
    )
    op.create_table(
        "property_price_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "event",
            sa.Enum("listed", "reduced", "increased", "relisted", "sold", name="price_event"),
            nullable=False,
        ),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("provenance_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_property_price_history_property_id_properties"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["data_provenance.id"],
            name=op.f("fk_property_price_history_provenance_id_data_provenance"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_price_history")),
    )
    op.create_index(
        op.f("ix_property_price_history_property_id"),
        "property_price_history",
        ["property_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_property_price_history_provenance_id"),
        "property_price_history",
        ["provenance_id"],
        unique=False,
    )
    op.create_table(
        "property_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum("manual", "pasted_text", "pdf", "screenshot", name="property_source_type"),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_payload_ref", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_property_sources_property_id_properties"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_sources")),
    )
    op.create_index(
        op.f("ix_property_sources_property_id"), "property_sources", ["property_id"], unique=False
    )
    op.create_table(
        "saved_properties",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_saved_properties_property_id_properties"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_saved_properties_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_properties")),
        sa.UniqueConstraint("user_id", "property_id", name="uq_saved_property"),
    )
    op.create_index(
        op.f("ix_saved_properties_property_id"), "saved_properties", ["property_id"], unique=False
    )
    op.create_index(
        op.f("ix_saved_properties_user_id"), "saved_properties", ["user_id"], unique=False
    )
    op.create_table(
        "ai_reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("numeric_guard_passed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["property_analyses.id"],
            name=op.f("fk_ai_reports_analysis_id_property_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_reports")),
    )
    op.create_index(op.f("ix_ai_reports_analysis_id"), "ai_reports", ["analysis_id"], unique=False)
    op.create_table(
        "analysis_factors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column(
            "component",
            sa.Enum(
                "affordability",
                "value",
                "personal_fit",
                "location",
                "property_quality",
                "investment",
                "risk",
                "market",
                name="factor_component",
            ),
            nullable=False,
        ),
        sa.Column(
            "direction",
            sa.Enum("positive", "negative", "neutral", name="factor_direction"),
            nullable=False,
        ),
        sa.Column("magnitude", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("sentence", sa.Text(), nullable=False),
        sa.Column("provenance_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["property_analyses.id"],
            name=op.f("fk_analysis_factors_analysis_id_property_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_factors")),
    )
    op.create_index(
        op.f("ix_analysis_factors_analysis_id"), "analysis_factors", ["analysis_id"], unique=False
    )
    op.create_table(
        "analysis_judgements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("ai_judgement_id", sa.UUID(), nullable=False),
        sa.Column(
            "component",
            sa.Enum(
                "affordability",
                "value",
                "personal_fit",
                "location",
                "property_quality",
                "investment",
                "risk",
                "market",
                name="judgement_component",
            ),
            nullable=False,
        ),
        sa.Column("applied_adjustment", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("capped", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ai_judgement_id"],
            ["ai_judgements.id"],
            name=op.f("fk_analysis_judgements_ai_judgement_id_ai_judgements"),
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["property_analyses.id"],
            name=op.f("fk_analysis_judgements_analysis_id_property_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_judgements")),
    )
    op.create_index(
        op.f("ix_analysis_judgements_ai_judgement_id"),
        "analysis_judgements",
        ["ai_judgement_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analysis_judgements_analysis_id"),
        "analysis_judgements",
        ["analysis_id"],
        unique=False,
    )
    op.create_table(
        "analysis_scores",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column(
            "component",
            sa.Enum(
                "affordability",
                "value",
                "personal_fit",
                "location",
                "property_quality",
                "investment",
                "risk",
                "market",
                name="score_component",
            ),
            nullable=False,
        ),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("raw_value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("subscore", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("base_weight", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("effective_weight", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("contribution", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("unavailable_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "NOT available OR subscore IS NOT NULL",
            name=op.f("ck_analysis_scores_available_subscore_has_value"),
        ),
        sa.CheckConstraint(
            "available OR unavailable_reason IS NOT NULL",
            name=op.f("ck_analysis_scores_unavailable_subscore_states_why"),
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["property_analyses.id"],
            name=op.f("fk_analysis_scores_analysis_id_property_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_scores")),
    )
    op.create_index(
        op.f("ix_analysis_scores_analysis_id"), "analysis_scores", ["analysis_id"], unique=False
    )
    op.create_table(
        "calculation_traces",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("step_name", sa.String(length=128), nullable=False),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("assumptions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rule_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["property_analyses.id"],
            name=op.f("fk_calculation_traces_analysis_id_property_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calculation_traces")),
    )
    op.create_index(
        op.f("ix_calculation_traces_analysis_id"),
        "calculation_traces",
        ["analysis_id"],
        unique=False,
    )
    op.create_table(
        "comparable_scores",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("comparable_id", sa.UUID(), nullable=False),
        sa.Column("similarity", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("distance_m", sa.Integer(), nullable=True),
        sa.Column("included", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("weight", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["property_analyses.id"],
            name=op.f("fk_comparable_scores_analysis_id_property_analyses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["comparable_id"],
            ["comparables.id"],
            name=op.f("fk_comparable_scores_comparable_id_comparables"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comparable_scores")),
    )
    op.create_index(
        op.f("ix_comparable_scores_analysis_id"), "comparable_scores", ["analysis_id"], unique=False
    )
    op.create_index(
        op.f("ix_comparable_scores_comparable_id"),
        "comparable_scores",
        ["comparable_id"],
        unique=False,
    )
    op.create_table(
        "financial_scenarios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("changed_assumptions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("outputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["property_analyses.id"],
            name=op.f("fk_financial_scenarios_analysis_id_property_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_scenarios")),
    )
    op.create_index(
        op.f("ix_financial_scenarios_analysis_id"),
        "financial_scenarios",
        ["analysis_id"],
        unique=False,
    )
    op.create_table(
        "risk_flags",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "flood",
                "zoning",
                "development",
                "environmental",
                "condition",
                "tax",
                "condo_fee",
                "special_assessment",
                "price_history",
                "insurance",
                "infrastructure",
                "noise",
                name="risk_category",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("confirmed", "potential", "unknown", name="risk_status"),
            nullable=False,
        ),
        sa.Column(
            "severity", sa.Enum("low", "medium", "high", name="risk_severity"), nullable=False
        ),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("provenance_id", sa.UUID(), nullable=False),
        sa.Column("distance_m", sa.Integer(), nullable=True),
        sa.Column("ai_judgement_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "ai_judgement_id IS NULL OR status = 'potential'",
            name=op.f("ck_risk_flags_ai_raises_only_potential"),
        ),
        sa.ForeignKeyConstraint(
            ["ai_judgement_id"],
            ["ai_judgements.id"],
            name=op.f("fk_risk_flags_ai_judgement_id_ai_judgements"),
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["property_analyses.id"],
            name=op.f("fk_risk_flags_analysis_id_property_analyses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provenance_id"],
            ["data_provenance.id"],
            name=op.f("fk_risk_flags_provenance_id_data_provenance"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_flags")),
    )
    op.create_index(
        op.f("ix_risk_flags_ai_judgement_id"), "risk_flags", ["ai_judgement_id"], unique=False
    )
    op.create_index(op.f("ix_risk_flags_analysis_id"), "risk_flags", ["analysis_id"], unique=False)
    op.create_index(
        op.f("ix_risk_flags_provenance_id"), "risk_flags", ["provenance_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_risk_flags_provenance_id"), table_name="risk_flags")
    op.drop_index(op.f("ix_risk_flags_analysis_id"), table_name="risk_flags")
    op.drop_index(op.f("ix_risk_flags_ai_judgement_id"), table_name="risk_flags")
    op.drop_table("risk_flags")
    op.drop_index(op.f("ix_financial_scenarios_analysis_id"), table_name="financial_scenarios")
    op.drop_table("financial_scenarios")
    op.drop_index(op.f("ix_comparable_scores_comparable_id"), table_name="comparable_scores")
    op.drop_index(op.f("ix_comparable_scores_analysis_id"), table_name="comparable_scores")
    op.drop_table("comparable_scores")
    op.drop_index(op.f("ix_calculation_traces_analysis_id"), table_name="calculation_traces")
    op.drop_table("calculation_traces")
    op.drop_index(op.f("ix_analysis_scores_analysis_id"), table_name="analysis_scores")
    op.drop_table("analysis_scores")
    op.drop_index(op.f("ix_analysis_judgements_analysis_id"), table_name="analysis_judgements")
    op.drop_index(op.f("ix_analysis_judgements_ai_judgement_id"), table_name="analysis_judgements")
    op.drop_table("analysis_judgements")
    op.drop_index(op.f("ix_analysis_factors_analysis_id"), table_name="analysis_factors")
    op.drop_table("analysis_factors")
    op.drop_index(op.f("ix_ai_reports_analysis_id"), table_name="ai_reports")
    op.drop_table("ai_reports")
    op.drop_index(op.f("ix_saved_properties_user_id"), table_name="saved_properties")
    op.drop_index(op.f("ix_saved_properties_property_id"), table_name="saved_properties")
    op.drop_table("saved_properties")
    op.drop_index(op.f("ix_property_sources_property_id"), table_name="property_sources")
    op.drop_table("property_sources")
    op.drop_index(
        op.f("ix_property_price_history_provenance_id"), table_name="property_price_history"
    )
    op.drop_index(
        op.f("ix_property_price_history_property_id"), table_name="property_price_history"
    )
    op.drop_table("property_price_history")
    op.drop_index(op.f("ix_property_attributes_superseded_by"), table_name="property_attributes")
    op.drop_index(op.f("ix_property_attributes_provenance_id"), table_name="property_attributes")
    op.drop_index(op.f("ix_property_attributes_property_id"), table_name="property_attributes")
    op.drop_index("ix_property_attributes_field", table_name="property_attributes")
    op.drop_table("property_attributes")
    op.drop_index("ix_property_analyses_user_recent", table_name="property_analyses")
    op.drop_index(op.f("ix_property_analyses_user_id"), table_name="property_analyses")
    op.drop_index(op.f("ix_property_analyses_rule_set_id"), table_name="property_analyses")
    op.drop_index(op.f("ix_property_analyses_property_id"), table_name="property_analyses")
    op.drop_index(op.f("ix_property_analyses_financial_profile_id"), table_name="property_analyses")
    op.drop_index(op.f("ix_property_analyses_buyer_preferences_id"), table_name="property_analyses")
    op.drop_table("property_analyses")
    op.drop_index(op.f("ix_market_snapshots_provenance_id"), table_name="market_snapshots")
    op.drop_table("market_snapshots")
    op.drop_index(op.f("ix_location_metrics_provenance_id"), table_name="location_metrics")
    op.drop_index(op.f("ix_location_metrics_location_id"), table_name="location_metrics")
    op.drop_table("location_metrics")
    op.drop_index(op.f("ix_comparables_provenance_id"), table_name="comparables")
    op.drop_index(op.f("ix_comparables_owner_user_id"), table_name="comparables")
    op.drop_index("ix_comparables_geom", table_name="comparables", postgresql_using="gist")
    op.drop_table("comparables")
    op.drop_index("ix_ai_judgements_property_type", table_name="ai_judgements")
    op.drop_index(op.f("ix_ai_judgements_property_id"), table_name="ai_judgements")
    op.drop_table("ai_judgements")
    op.drop_index(op.f("ix_user_profiles_user_id"), table_name="user_profiles")
    op.drop_table("user_profiles")
    op.drop_index(op.f("ix_property_comparisons_user_id"), table_name="property_comparisons")
    op.drop_table("property_comparisons")
    op.drop_index("ix_properties_geom", table_name="properties", postgresql_using="gist")
    op.drop_index(op.f("ix_properties_created_by_user_id"), table_name="properties")
    op.drop_table("properties")
    op.drop_index(op.f("ix_financial_profiles_user_id"), table_name="financial_profiles")
    op.drop_table("financial_profiles")
    op.drop_index(
        "ix_data_provenance_expiring",
        table_name="data_provenance",
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )
    op.drop_index(op.f("ix_data_provenance_data_source_id"), table_name="data_provenance")
    op.drop_table("data_provenance")
    op.drop_index(op.f("ix_buyer_preferences_user_id"), table_name="buyer_preferences")
    op.drop_table("buyer_preferences")
    op.drop_index(op.f("ix_audit_logs_actor_user_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("users")
    op.drop_index("ix_rules_lookup", table_name="rules", postgresql_where=sa.text("active"))
    op.drop_table("rules")
    op.drop_table("rule_sets")
    op.drop_index("ix_locations_geom", table_name="locations", postgresql_using="gist")
    op.drop_table("locations")
    op.drop_table("data_sources")

    # Postgres keeps a named ENUM after the last table using it is dropped, so a
    # downgrade followed by an upgrade fails on 'type already exists' unless the
    # types go too. Verified by running downgrade base && upgrade head.
    op.execute("DROP TYPE IF EXISTS ai_judgement_type")
    op.execute("DROP TYPE IF EXISTS buyer_goal")
    op.execute("DROP TYPE IF EXISTS comp_kind")
    op.execute("DROP TYPE IF EXISTS credit_score_band")
    op.execute("DROP TYPE IF EXISTS factor_component")
    op.execute("DROP TYPE IF EXISTS factor_direction")
    op.execute("DROP TYPE IF EXISTS judgement_component")
    op.execute("DROP TYPE IF EXISTS licence_class")
    op.execute("DROP TYPE IF EXISTS price_event")
    op.execute("DROP TYPE IF EXISTS property_kind")
    op.execute("DROP TYPE IF EXISTS property_source_type")
    op.execute("DROP TYPE IF EXISTS residency_status")
    op.execute("DROP TYPE IF EXISTS risk_category")
    op.execute("DROP TYPE IF EXISTS risk_posture")
    op.execute("DROP TYPE IF EXISTS risk_severity")
    op.execute("DROP TYPE IF EXISTS risk_status")
    op.execute("DROP TYPE IF EXISTS rule_verification")
    op.execute("DROP TYPE IF EXISTS score_component")
    op.execute("DROP TYPE IF EXISTS source_class")
    op.execute("DROP TYPE IF EXISTS time_horizon")
