"""Analyses, their working, their risks, and the AI judgements that fed them.

An analysis is immutable. There is no UPDATE path: a re-run inserts a new row, so
a user can be shown what changed and why, and so a score can never quietly differ
from the one they read yesterday.

``ai_judgements`` is the channel from ADR 0004. A judgement is **pinned** — model
id, prompt hash, sampling parameters and the validated output are stored — and the
analysis references it by id. That is what lets a nondeterministic model
contribute to a reproducible score: we do not re-ask the model, we replay what it
said. ``influence_cap`` travels with the row, so the bound on how far a judgement
can move a subscore is recorded evidence rather than a constant in whatever
version of the scoring code happens to be deployed.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, money, uuid_fk, uuid_pk

COMPONENTS = (
    "affordability",
    "value",
    "personal_fit",
    "location",
    "property_quality",
    "investment",
    "risk",
    "market",
)
DIRECTIONS = ("positive", "negative", "neutral")
RISK_CATEGORIES = (
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
)
RISK_STATUSES = ("confirmed", "potential", "unknown")
RISK_SEVERITIES = ("low", "medium", "high")
JUDGEMENT_TYPES = (
    "condition_signal",
    "listing_red_flags",
    "omission_signals",
    "preference_interpretation",
    "decision_review",
)


class PropertyAnalysis(Base):
    """One immutable run."""

    __tablename__ = "property_analyses"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id")
    property_id: Mapped[uuid.UUID] = uuid_fk("properties.id")
    financial_profile_id: Mapped[uuid.UUID] = uuid_fk("financial_profiles.id")
    buyer_preferences_id: Mapped[uuid.UUID] = uuid_fk("buyer_preferences.id")
    rule_set_id: Mapped[uuid.UUID] = uuid_fk("rule_sets.id")

    scoring_model_version: Mapped[str] = mapped_column(String(16), nullable=False)
    buy_score: Mapped[int | None] = mapped_column(SmallInteger)
    """Nullable on purpose: past 35% unavailable weight the model withholds it."""

    score_withheld_reason: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    weights_applied: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False)
    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    """sha256 over the canonical input bundle, pinned AI judgements included."""

    fair_value_low_cents = money(nullable=True)
    fair_value_high_cents = money(nullable=True)
    suggested_offer_low_cents = money(nullable=True)
    suggested_offer_high_cents = money(nullable=True)
    monthly_ownership_cost_cents = money(nullable=True)
    closing_costs_cents = money(nullable=True)
    cash_required_cents = money(nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "buy_score IS NOT NULL OR score_withheld_reason IS NOT NULL",
            name="withheld_score_states_why",
        ),
        CheckConstraint(
            "buy_score IS NULL OR (buy_score >= 0 AND buy_score <= 100)",
            name="buy_score_in_range",
        ),
        CheckConstraint(
            "fair_value_high_cents IS NULL OR fair_value_low_cents IS NULL "
            "OR fair_value_high_cents >= fair_value_low_cents",
            name="fair_value_is_a_range",
        ),
        Index("ix_property_analyses_user_recent", "user_id", "created_at"),
    )


class AnalysisScore(Base):
    __tablename__ = "analysis_scores"

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = uuid_fk("property_analyses.id", ondelete="CASCADE")
    component: Mapped[str] = mapped_column(
        Enum(*COMPONENTS, name="score_component"), nullable=False
    )
    available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    raw_value: Mapped[float | None] = mapped_column(Numeric(18, 6))
    subscore: Mapped[float | None] = mapped_column(Numeric(6, 3))
    base_weight: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    effective_weight: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    contribution: Mapped[float] = mapped_column(Numeric(7, 4), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    unavailable_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "available OR unavailable_reason IS NOT NULL", name="unavailable_subscore_states_why"
        ),
        CheckConstraint(
            "NOT available OR subscore IS NOT NULL", name="available_subscore_has_value"
        ),
    )


class AnalysisFactor(Base):
    """The sentences the UI renders and the explainer is allowed to use.

    If a factor is not a row here, it may not appear in an explanation. That is
    the claim-level sibling of the numeric-token guard.
    """

    __tablename__ = "analysis_factors"

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = uuid_fk("property_analyses.id", ondelete="CASCADE")
    component: Mapped[str] = mapped_column(
        Enum(*COMPONENTS, name="factor_component"), nullable=False
    )
    direction: Mapped[str] = mapped_column(
        Enum(*DIRECTIONS, name="factor_direction"), nullable=False
    )
    magnitude: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    sentence: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_ids: Mapped[list[str] | None] = mapped_column(JSONB)


class RiskFlag(Base):
    __tablename__ = "risk_flags"

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = uuid_fk("property_analyses.id", ondelete="CASCADE")
    category: Mapped[str] = mapped_column(
        Enum(*RISK_CATEGORIES, name="risk_category"), nullable=False
    )
    status: Mapped[str] = mapped_column(Enum(*RISK_STATUSES, name="risk_status"), nullable=False)
    severity: Mapped[str] = mapped_column(
        Enum(*RISK_SEVERITIES, name="risk_severity"), nullable=False
    )
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_id: Mapped[uuid.UUID] = uuid_fk("data_provenance.id")
    distance_m: Mapped[int | None] = mapped_column(Integer)
    ai_judgement_id: Mapped[uuid.UUID | None] = uuid_fk("ai_judgements.id", nullable=True)

    __table_args__ = (
        # ADR 0004: a model may raise a suspicion, never confirm one. CONFIRMED
        # requires a data source, and this is where that stops being a convention.
        CheckConstraint(
            "ai_judgement_id IS NULL OR status = 'potential'",
            name="ai_raises_only_potential",
        ),
    )


class CalculationTrace(Base):
    """Every financial figure's working, stored so the UI can show it."""

    __tablename__ = "calculation_traces"

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = uuid_fk("property_analyses.id", ondelete="CASCADE")
    step_name: Mapped[str] = mapped_column(String(128), nullable=False)
    formula: Mapped[str] = mapped_column(Text, nullable=False)
    inputs: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(16))
    assumptions: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    rule_ids: Mapped[list[str] | None] = mapped_column(JSONB)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ComparableScore(Base):
    __tablename__ = "comparable_scores"

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = uuid_fk("property_analyses.id", ondelete="CASCADE")
    comparable_id: Mapped[uuid.UUID] = uuid_fk("comparables.id", ondelete="CASCADE")
    similarity: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    distance_m: Mapped[int | None] = mapped_column(Integer)
    included: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    """Plain language, for inclusion and exclusion alike. Silent filters cost trust."""

    weight: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)


class FinancialScenario(Base, TimestampMixin):
    __tablename__ = "financial_scenarios"

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = uuid_fk("property_analyses.id", ondelete="CASCADE")
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    changed_assumptions: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    outputs: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class AiJudgement(Base):
    """A pinned model judgement (ADR 0004).

    Pinned, not regenerated: temperature 0 is not determinism, so the only honest
    way to keep a model inside a reproducible pipeline is to store what it said
    and replay that. Re-asking produces a new judgement and therefore a new
    analysis.
    """

    __tablename__ = "ai_judgements"

    id: Mapped[uuid.UUID] = uuid_pk()
    property_id: Mapped[uuid.UUID] = uuid_fk("properties.id", ondelete="CASCADE")
    judgement_type: Mapped[str] = mapped_column(
        Enum(*JUDGEMENT_TYPES, name="ai_judgement_type"), nullable=False
    )
    output: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    """Validated against the judgement's schema. A malformed judgement is discarded,
    never repaired."""

    evidence: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    """Quoted spans. A judgement with no supporting text is dropped."""

    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    influence_cap: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    """Maximum points this judgement may move its subscore. Stored, not assumed."""

    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    """The exact tag, e.g. ``llama3.1:8b-instruct-q4_K_M`` — never ``llama3``."""

    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sampling: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    judgement_version: Mapped[str] = mapped_column(String(16), nullable=False)
    numeric_guard_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    user_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Set for preference_interpretation once the user confirms, at which point the
    judgement's provenance is rewritten as user_asserted — because they really did
    say it, we only parsed it."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="judgement_confidence_fraction"
        ),
        CheckConstraint("influence_cap >= 0", name="influence_cap_is_positive"),
        Index("ix_ai_judgements_property_type", "property_id", "judgement_type"),
    )


class AnalysisJudgement(Base):
    """Which pinned judgements an analysis consumed, and what they actually moved."""

    __tablename__ = "analysis_judgements"

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = uuid_fk("property_analyses.id", ondelete="CASCADE")
    ai_judgement_id: Mapped[uuid.UUID] = uuid_fk("ai_judgements.id")
    component: Mapped[str] = mapped_column(
        Enum(*COMPONENTS, name="judgement_component"), nullable=False
    )
    applied_adjustment: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    capped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    """True when the cap bound the adjustment — worth counting, because a judgement
    that is always capped is a judgement that is calibrated wrong."""


class AiReport(Base):
    """The narration layer: prose over a finished analysis."""

    __tablename__ = "ai_reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    analysis_id: Mapped[uuid.UUID] = uuid_fk("property_analyses.id", ondelete="CASCADE")
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    numeric_guard_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    """Stored because "the model tried to invent a number" is an event worth counting."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PropertyComparison(Base, TimestampMixin):
    __tablename__ = "property_comparisons"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk("users.id", ondelete="CASCADE")
    analysis_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    verdicts: Mapped[dict[str, object] | None] = mapped_column(JSONB)
