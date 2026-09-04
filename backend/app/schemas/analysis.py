"""API request and response shapes, per docs/API.md.

Two conventions are enforced by the types rather than by convention:

* every monetary field is an integer of cents and its name ends ``_cents``;
* every derived value ships inside an :class:`Envelope` carrying its provenance,
  and an unavailable value carries a **required** reason.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Envelope(BaseModel):
    """A value that knows where it came from. ``value: null`` requires a reason."""

    model_config = ConfigDict(extra="forbid")

    value: Any = None
    unit: str | None = None
    source_class: str
    confidence: float | None = None
    as_of: str | None = None
    reason: str | None = None
    sources: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unavailable_states_why(self) -> Self:
        if self.value is None and not self.reason:
            raise ValueError("an unavailable value must carry a reason")
        return self


class BuyerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gross_annual_income_cents: int = Field(gt=0)
    household_income_cents: int = Field(gt=0)
    monthly_debt_payments_cents: int = Field(ge=0, default=0)
    down_payment_cents: int = Field(gt=0)
    available_savings_cents: int = Field(ge=0, default=0)
    emergency_fund_cents: int = Field(ge=0, default=0)
    desired_max_monthly_cents: int | None = Field(default=None, gt=0)
    first_time_buyer: bool = False
    residency_status: Literal["citizen_or_pr", "foreign_national", "unknown"] = "unknown"


class PropertyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_price_cents: int = Field(gt=0)
    jurisdiction: str = "ON/Toronto"
    property_kind: Literal[
        "detached", "semi", "townhouse", "condo_apartment", "condo_town", "duplex", "other"
    ] = "detached"
    annual_property_tax_cents: int | None = Field(default=None, ge=0)
    monthly_condo_fee_cents: int | None = Field(default=None, ge=0)
    square_feet: int | None = Field(default=None, gt=0)
    year_built: int | None = Field(default=None, ge=1700, le=2100)
    bedrooms: int | None = Field(default=None, ge=0)
    bathrooms: Decimal | None = Field(default=None, ge=0)
    has_parking: bool | None = None
    is_new_build: bool = False


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_bedrooms: int | None = Field(default=None, ge=0)
    min_bathrooms: int | None = Field(default=None, ge=0)
    requires_parking: bool | None = None
    max_commute_minutes: int | None = Field(default=None, gt=0)
    commute_minutes: int | None = Field(default=None, ge=0)
    goal: Literal["primary_residence", "investment", "house_hack", "mixed"] | None = None
    time_horizon: Literal["under_3", "3_to_5", "5_to_10", "over_10"] | None = None
    risk_posture: Literal["conservative", "balanced", "aggressive"] | None = None
    has_children: bool | None = None
    schools_importance: int | None = Field(default=None, ge=0, le=5)


class ComparableIn(BaseModel):
    """A sold comparable the user supplies (ADR 0002 §3)."""

    model_config = ConfigDict(extra="forbid")

    address: str
    sale_price_cents: int = Field(gt=0)
    sale_date: str
    square_feet: int | None = Field(default=None, gt=0)
    bedrooms: int | None = Field(default=None, ge=0)
    distance_m: int | None = Field(default=None, ge=0)


class MortgageTermsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_rate: Decimal = Field(gt=0, lt=1)
    amortization_years: int = Field(ge=5, le=30)


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    property: PropertyIn
    buyer: BuyerIn
    terms: MortgageTermsIn
    preferences: PreferencesIn = Field(default_factory=PreferencesIn)
    comparables: list[ComparableIn] = Field(default_factory=list)


class ScoreOut(BaseModel):
    component: str
    available: bool
    subscore: float | None
    base_weight: float
    effective_weight: float
    contribution: float
    confidence: float
    unavailable_reason: str | None = None


class FactorOut(BaseModel):
    component: str
    direction: str
    magnitude: float
    sentence: str


class RiskOut(BaseModel):
    category: str
    status: str
    severity: str
    evidence: str
    explanation: str
    recommended_action: str
    distance_m: int | None = None


class TraceOut(BaseModel):
    name: str
    formula: str
    inputs: dict[str, Any]
    output: Any
    unit: str | None = None
    rule_keys: list[str] = Field(default_factory=list)


class AssumptionOut(BaseModel):
    key: str
    value: Any
    rationale: str


class MoneyOut(BaseModel):
    purchase_price_cents: int
    down_payment_cents: int
    mortgage_principal_cents: int
    insurance_premium_cents: int
    monthly_ownership_cost_cents: int
    closing_costs_cents: int
    cash_required_cents: int
    cash_shortfall_cents: int


class QualificationOut(BaseModel):
    may_qualify: bool
    stressed_rate: float
    gds: float
    tds: float
    gds_limit: float
    tds_limit: float
    insured_eligible: bool
    max_purchase_price_cents: int | None
    blocking_reasons: list[str]
    disclaimer: str


class FairValueOut(BaseModel):
    low_cents: int
    high_cents: int
    basis: str
    confidence: float
    note: str


class AnalyzeResponse(BaseModel):
    """The analysis payload. ``buy_score`` is nullable on purpose."""

    scoring_model_version: str
    rule_set: str
    buy_score: int | None
    score_withheld_reason: str | None
    confidence: float
    inputs_hash: str
    scores: list[ScoreOut]
    factors: dict[str, list[FactorOut]]
    money: MoneyOut
    closing_cost_lines: list[dict[str, Any]]
    qualification: QualificationOut
    fair_value: FairValueOut
    risks: list[RiskOut]
    traces: list[TraceOut]
    assumptions: list[AssumptionOut]
    unavailable: list[dict[str, str]]
    disclaimer: str = (
        "This analysis is for informational purposes and is not financial, mortgage, legal, "
        "tax, insurance, or home-inspection advice."
    )


class ParseListingRequest(BaseModel):
    """Text the user already has. We never fetch a URL (ADR 0002 §2)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=40_000)
    source_url: str | None = None
    """Recorded for the user's own reference, and never retrieved."""


class ParseListingResponse(BaseModel):
    fields: dict[str, Any]
    fields_as_cents: dict[str, int]
    evidence: dict[str, str]
    """The exact span each value was read from, so the user can check it."""

    rejected: dict[str, str]
    read_by: str
    requires_confirmation: bool = True
    note: str
