"""Who may do what, as a pure function of an account's state.

No I/O here: the service layer gathers the facts (role, active subscriptions,
the credit ledger) and this decides. That keeps every rule about money and access
in one place a unit test can exhaust, and it means the frontend never decides
anything — it renders what this returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.billing.config import AdsConfig, PlanFeatures, PricingConfig

Tier = Literal["free", "paid", "professional", "admin"]
CreditSource = Literal["unlimited", "plan", "free"]

#: When two subscriptions are active, the richer one governs.
PLAN_PRECEDENCE = ("professional", "property_watch")


@dataclass(frozen=True, slots=True)
class AccountState:
    role: str
    active_subscriptions: tuple[str, ...] = ()
    has_purchase: bool = False
    free_used: int = 0
    promo_analyses: int = 0
    plan_used_this_month: int = 0


@dataclass(frozen=True, slots=True)
class Entitlements:
    tier: Tier
    unlimited: bool
    plan_key: str | None
    free_total: int
    free_used: int
    free_remaining: int
    plan_monthly_cap: int | None
    plan_used_this_month: int
    plan_remaining: int | None
    next_credit_source: CreditSource | None
    """What the next analysis will draw on; None means it cannot run."""

    deep_dive_included: bool
    watch_limit: int | None
    compare_max: int
    show_ads: bool

    @property
    def can_analyze(self) -> bool:
        return self.next_credit_source is not None


def _plan_for(state: AccountState) -> str | None:
    if state.role == "professional":
        return "professional"
    for key in PLAN_PRECEDENCE:
        if key in state.active_subscriptions:
            return key
    # A subscription product an admin added later still counts.
    return state.active_subscriptions[0] if state.active_subscriptions else None


def entitlements(state: AccountState, pricing: PricingConfig, ads: AdsConfig) -> Entitlements:
    free_total = pricing.free_analyses + state.promo_analyses
    free_remaining = max(0, free_total - state.free_used)

    if state.role == "admin":
        return Entitlements(
            tier="admin",
            unlimited=True,
            plan_key=None,
            free_total=free_total,
            free_used=state.free_used,
            free_remaining=free_remaining,
            plan_monthly_cap=None,
            plan_used_this_month=state.plan_used_this_month,
            plan_remaining=None,
            next_credit_source="unlimited",
            deep_dive_included=True,
            watch_limit=None,
            compare_max=5,
            show_ads=False,
        )

    plan_key = _plan_for(state)
    product = pricing.product(plan_key) if plan_key else None
    features: PlanFeatures = (
        product.features if product and product.features else pricing.free_features
    )

    plan_cap = features.analyses_per_month if plan_key else None
    plan_remaining: int | None = None
    source: CreditSource | None = None
    if plan_key:
        if plan_cap is None:
            source = "plan"
        else:
            plan_remaining = max(0, plan_cap - state.plan_used_this_month)
            if plan_remaining > 0:
                source = "plan"
    if source is None and free_remaining > 0:
        source = "free"

    tier: Tier
    if plan_key == "professional":
        tier = "professional"
    elif plan_key or state.has_purchase:
        tier = "paid"
    else:
        tier = "free"

    audience = {
        "free": ads.show_to_free,
        "paid": ads.show_to_paid,
        "professional": ads.show_to_professional,
    }[tier]

    return Entitlements(
        tier=tier,
        unlimited=False,
        plan_key=plan_key,
        free_total=free_total,
        free_used=state.free_used,
        free_remaining=free_remaining,
        plan_monthly_cap=plan_cap,
        plan_used_this_month=state.plan_used_this_month,
        plan_remaining=plan_remaining,
        next_credit_source=source,
        deep_dive_included=features.deep_dive_included,
        watch_limit=features.watch_limit,
        compare_max=features.compare_max,
        show_ads=ads.enabled and audience,
    )
