"""Everything an admin can change without a deploy, with the defaults it starts from.

Stored as JSON rows in ``system_settings`` and validated by these models on the
way in and on the way out, so a bad edit is refused at the form rather than
discovered by a checkout that charges the wrong amount.

The defaults are the brief's suggested launch prices. They are suggestions, not
constants: nothing outside this module and the admin console names a price.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AD_SLOTS = (
    "AD_SLOT_TOP_BANNER",
    "AD_SLOT_RESULTS_SIDEBAR",
    "AD_SLOT_BETWEEN_SECTIONS",
    "AD_SLOT_DASHBOARD",
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanFeatures(_Strict):
    analyses_per_month: int | None = Field(default=None, ge=0)
    """None means no monthly cap beyond the hourly rate limit."""

    deep_dive_included: bool = False
    watch_limit: int = Field(default=0, ge=0)
    compare_max: int = Field(default=5, ge=2, le=5)


class Product(_Strict):
    key: str = Field(pattern=r"^[a-z_]{3,32}$")
    name: str = Field(min_length=1, max_length=64)
    kind: Literal["one_time", "subscription"]
    price_cents: int = Field(ge=0, le=100_000_00)
    interval: Literal["month", "year"] | None = None
    description: str = Field(default="", max_length=400)
    features: PlanFeatures | None = None
    """Subscriptions only: what an active subscriber gets."""

    active: bool = True

    @model_validator(mode="after")
    def subscription_shape(self) -> Product:
        if self.kind == "subscription" and (self.interval is None or self.features is None):
            raise ValueError(f"{self.key}: a subscription needs an interval and features")
        if self.kind == "one_time" and self.interval is not None:
            raise ValueError(f"{self.key}: a one-time product has no interval")
        return self


class PricingConfig(_Strict):
    currency: Literal["CAD", "USD"] = "CAD"
    free_analyses: int = Field(default=5, ge=0, le=1000)
    free_features: PlanFeatures = PlanFeatures(
        analyses_per_month=None, deep_dive_included=False, watch_limit=0, compare_max=5
    )
    products: list[Product] = [
        Product(
            key="deep_dive",
            name="Deep Dive Report",
            kind="one_time",
            price_cents=999,
            description="The complete 5- and 10-year analysis of one property, with a PDF.",
        ),
        Product(
            key="property_watch",
            name="Property Watch",
            kind="subscription",
            price_cents=2900,
            interval="month",
            description="Keep analysing, save properties to watch, and see how a price "
            "change moves your numbers.",
            features=PlanFeatures(
                analyses_per_month=30, deep_dive_included=False, watch_limit=10, compare_max=5
            ),
        ),
        Product(
            key="professional",
            name="Professional",
            kind="subscription",
            price_cents=4900,
            interval="month",
            description="For people analysing properties every week: Deep Dives included, "
            "more watches, a higher monthly allowance.",
            features=PlanFeatures(
                analyses_per_month=200, deep_dive_included=True, watch_limit=50, compare_max=5
            ),
        ),
    ]

    @field_validator("products")
    @classmethod
    def unique_keys(cls, products: list[Product]) -> list[Product]:
        keys = [p.key for p in products]
        if len(keys) != len(set(keys)):
            raise ValueError("product keys must be unique")
        if "deep_dive" not in keys:
            raise ValueError("the deep_dive product must exist (it can be made inactive)")
        return products

    def product(self, key: str) -> Product | None:
        return next((p for p in self.products if p.key == key), None)


class AdsConfig(_Strict):
    enabled: bool = True
    provider: Literal["none", "adsense"] = "none"
    """``none`` renders nothing in production and a labelled placeholder in
    development. No network is wired in until an admin chooses one."""

    adsense_client: str = Field(default="", max_length=64, pattern=r"^(ca-pub-\d{6,20})?$")
    show_to_free: bool = True
    show_to_paid: bool = False
    show_to_professional: bool = False
    slots: dict[str, bool] = {slot: True for slot in AD_SLOTS}

    @field_validator("slots")
    @classmethod
    def known_slots(cls, slots: dict[str, bool]) -> dict[str, bool]:
        unknown = set(slots) - set(AD_SLOTS)
        if unknown:
            raise ValueError(f"unknown ad slots: {sorted(unknown)}")
        return {slot: slots.get(slot, False) for slot in AD_SLOTS}


class FeatureFlags(_Strict):
    signups: bool = True
    deep_dive: bool = True
    property_watch: bool = True
    comparison: bool = True
    offer_scenarios: bool = True
    ai_explanations: bool = True
    """Still needs PDE_LLM_EXPLANATIONS_ENABLED and a reachable model. This switch can
    only turn explanations off, never conjure a model."""


class Promotion(_Strict):
    code: str = Field(pattern=r"^[A-Z0-9_-]{3,32}$")
    description: str = Field(default="", max_length=200)
    kind: Literal["extra_analyses", "percent_off"]
    value: int = Field(ge=1, le=100)
    """Analyses granted, or percent off the first payment."""

    applies_to: list[str] = []
    """Product keys a percent_off applies to; empty means all."""

    active: bool = True
    expires_on: date | None = None


class PromotionsConfig(_Strict):
    promotions: list[Promotion] = []

    def find(self, code: str, today: date) -> Promotion | None:
        code = code.strip().upper()
        for promo in self.promotions:
            if (
                promo.code == code
                and promo.active
                and (promo.expires_on is None or promo.expires_on >= today)
            ):
                return promo
        return None


class CostAssumptions(_Strict):
    """What the admin says things cost. Every figure derived from these is an estimate."""

    payment_fee_percent: Decimal = Field(default=Decimal("2.9"), ge=0, le=20)
    payment_fee_fixed_cents: int = Field(default=30, ge=0, le=1000)
    infrastructure_monthly_cents: int = Field(default=0, ge=0)
    other_monthly_cents: int = Field(default=0, ge=0)
    ai_input_cost_per_million_tokens_cents: Decimal = Field(default=Decimal(0), ge=0)
    ai_output_cost_per_million_tokens_cents: Decimal = Field(default=Decimal(0), ge=0)
    ai_cost_per_call_cents: Decimal = Field(default=Decimal(0), ge=0)
    """Used when the provider does not report token counts."""

    location_cost_per_call_cents: Decimal = Field(default=Decimal(0), ge=0)


class ProjectionConfig(_Strict):
    """Deep Dive assumptions. Shown beside every figure they produce."""

    appreciation_rates: list[Decimal] = [Decimal("0"), Decimal("0.02"), Decimal("0.04")]
    selling_cost_rate: Decimal = Field(default=Decimal("0.05"), ge=0, le=Decimal("0.15"))
    opportunity_return_rate: Decimal = Field(default=Decimal("0.05"), ge=0, le=Decimal("0.2"))
    property_tax_growth: Decimal = Field(default=Decimal("0.03"), ge=0, le=Decimal("0.2"))
    condo_fee_growth: Decimal = Field(default=Decimal("0.04"), ge=0, le=Decimal("0.2"))
    insurance_growth: Decimal = Field(default=Decimal("0.03"), ge=0, le=Decimal("0.2"))
    maintenance_growth: Decimal = Field(default=Decimal("0.02"), ge=0, le=Decimal("0.2"))
    utilities_growth: Decimal = Field(default=Decimal("0.02"), ge=0, le=Decimal("0.2"))

    @field_validator("appreciation_rates")
    @classmethod
    def sensible_rates(cls, rates: list[Decimal]) -> list[Decimal]:
        if not 1 <= len(rates) <= 5:
            raise ValueError("between one and five appreciation scenarios")
        if any(r < Decimal("-0.1") or r > Decimal("0.15") for r in rates):
            raise ValueError("appreciation rates must be between -10% and 15% a year")
        if Decimal(0) not in rates:
            raise ValueError("the no-appreciation scenario (0) is always shown")
        return sorted(rates)


SETTINGS_MODELS: dict[str, type[BaseModel]] = {
    "pricing": PricingConfig,
    "ads": AdsConfig,
    "features": FeatureFlags,
    "promotions": PromotionsConfig,
    "costs": CostAssumptions,
    "projection": ProjectionConfig,
}
