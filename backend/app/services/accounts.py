"""Gathering an account's facts for the entitlement rules, and recording what happened.

The rules themselves live in ``billing/entitlements.py`` and are pure. This module
is the I/O on either side of them: read the ledger, and append to it.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.config import AdsConfig, PricingConfig
from app.billing.entitlements import AccountState, Entitlements, entitlements
from app.models.account import (
    Payment,
    ProductEvent,
    PromoRedemption,
    Subscription,
    UsageEvent,
)
from app.models.user import User
from app.services import settings_store

ACTIVE_SUBSCRIPTION_STATUSES = ("active", "trialing")

#: The only analytics events accepted, from the server or the browser. Anything
#: else is dropped: a free-form event stream is how financial values leak into
#: analytics without anyone deciding they should.
SERVER_EVENTS = frozenset(
    {
        "signup_completed",
        "analysis_completed",
        "free_analysis_used",
        "free_limit_reached",
        "deep_dive_checkout_started",
        "subscription_checkout_started",
        "payment_succeeded",
        "property_watch_created",
        "comparison_created",
        "offer_scenarios_run",
    }
)
CLIENT_EVENTS = frozenset(
    {
        "landing_viewed",
        "analysis_started",
        "deep_dive_viewed",
        "subscription_viewed",
        "pricing_viewed",
        "upgrade_clicked",
    }
)

log = logging.getLogger(__name__)


def month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def active_subscriptions(
    db: AsyncSession, user_id: uuid.UUID, now: datetime
) -> list[Subscription]:
    rows = (
        await db.scalars(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
            )
        )
    ).all()
    live = []
    for sub in rows:
        end = sub.current_period_end
        if end is not None and end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        if end is None or end > now:
            live.append(sub)
    return live


async def account_state(db: AsyncSession, user: User, now: datetime) -> AccountState:
    free_used = await db.scalar(
        select(func.count())
        .select_from(UsageEvent)
        .where(
            UsageEvent.user_id == user.id,
            UsageEvent.kind == "analysis",
            UsageEvent.credit_source == "free",
        )
    )
    plan_used = await db.scalar(
        select(func.count())
        .select_from(UsageEvent)
        .where(
            UsageEvent.user_id == user.id,
            UsageEvent.kind == "analysis",
            UsageEvent.credit_source == "plan",
            UsageEvent.at >= month_start(now),
        )
    )
    promo = await db.scalar(
        select(func.coalesce(func.sum(PromoRedemption.value), 0)).where(
            PromoRedemption.user_id == user.id, PromoRedemption.kind == "extra_analyses"
        )
    )
    purchased = await db.scalar(
        select(func.count())
        .select_from(Payment)
        .where(Payment.user_id == user.id, Payment.status == "succeeded")
    )
    subs = await active_subscriptions(db, user.id, now)
    return AccountState(
        role=user.role,
        active_subscriptions=tuple(s.product_key for s in subs),
        has_purchase=bool(purchased),
        free_used=int(free_used or 0),
        promo_analyses=int(promo or 0),
        plan_used_this_month=int(plan_used or 0),
    )


async def entitlements_for(
    db: AsyncSession, user: User, now: datetime | None = None
) -> Entitlements:
    now = now or datetime.now(UTC)
    pricing = await settings_store.load(db, "pricing", PricingConfig)
    ads = await settings_store.load(db, "ads", AdsConfig)
    return entitlements(await account_state(db, user, now), pricing, ads)


def usage_summary(ent: Entitlements) -> dict[str, Any]:
    """The shape the browser renders. It displays these; it never computes them."""
    return {
        "tier": ent.tier,
        "unlimited": ent.unlimited,
        "plan_key": ent.plan_key,
        "free_total": ent.free_total,
        "free_used": ent.free_used,
        "free_remaining": ent.free_remaining,
        "plan_monthly_cap": ent.plan_monthly_cap,
        "plan_used_this_month": ent.plan_used_this_month,
        "plan_remaining": ent.plan_remaining,
        "can_analyze": ent.can_analyze,
        "deep_dive_included": ent.deep_dive_included,
        "watch_limit": ent.watch_limit,
        "compare_max": ent.compare_max,
        "show_ads": ent.show_ads,
    }


def record_event(
    db: AsyncSession,
    name: str,
    user_id: uuid.UUID | None,
    properties: dict[str, str | int | bool] | None = None,
) -> None:
    """Queue an analytics event on the caller's transaction.

    Properties are limited to short labels and small integers; a value that looks
    like money is refused outright rather than trusted to the caller.
    """
    if name not in SERVER_EVENTS | CLIENT_EVENTS:
        log.warning("Dropped unknown analytics event %s", name)
        return
    clean: dict[str, str | int | bool] = {}
    for key, value in (properties or {}).items():
        if key.endswith("_cents") or "income" in key or "price" in key:
            continue
        if isinstance(value, str):
            clean[key] = value[:64]
        elif isinstance(value, bool) or (isinstance(value, int) and abs(value) < 10_000):
            clean[key] = value
    db.add(ProductEvent(user_id=user_id, name=name, properties=clean or None))
