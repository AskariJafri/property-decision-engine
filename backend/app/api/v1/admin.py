"""The admin console's API. Every route depends on ``require_admin``.

Metrics are counted from rows that exist — users, analyses, the credit ledger,
verified payments, recorded API calls. Where a number needs something the
product does not have (ad impressions without an ad network, an actual AI bill
without token prices), the response says ``null`` with a reason rather than a
plausible-looking figure.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import AdminUser, DbSession
from app.billing.config import SETTINGS_MODELS, AdsConfig, CostAssumptions
from app.core.config import get_settings
from app.models.account import (
    ApiUsage,
    ErrorEvent,
    Payment,
    ProductEvent,
    PropertyWatch,
    Subscription,
    UsageEvent,
)
from app.models.analysis import PropertyAnalysis, PropertyComparison
from app.models.user import AuditLog, User
from app.services import accounts, settings_store

router = APIRouter(prefix="/api/v1/admin")

LIMIT = Query(default=100, ge=1, le=500)
SEARCH = Query(default="", max_length=100)


async def _count(db: AsyncSession, stmt: Any) -> int:
    return int(await db.scalar(stmt) or 0)


def _money(value: Any) -> int:
    return int(Decimal(str(value or 0)).quantize(Decimal("1")))


async def _tier_sets(db: AsyncSession, now: datetime) -> dict[str, set[uuid.UUID]]:
    users = (await db.execute(select(User.id, User.role).where(User.deleted_at.is_(None)))).all()
    subs = (
        await db.execute(
            select(
                Subscription.user_id, Subscription.product_key, Subscription.current_period_end
            ).where(Subscription.status.in_(accounts.ACTIVE_SUBSCRIPTION_STATUSES))
        )
    ).all()
    payers = set(
        (await db.scalars(select(Payment.user_id).where(Payment.status == "succeeded"))).all()
    )
    live_subs: dict[uuid.UUID, set[str]] = {}
    for user_id, product, end in subs:
        if end is not None and end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        if end is None or end > now:
            live_subs.setdefault(user_id, set()).add(product)

    admins = {u for u, role in users if role == "admin"}
    professional = {
        u
        for u, role in users
        if u not in admins and (role == "professional" or "professional" in live_subs.get(u, ()))
    }
    paid = {
        u
        for u, _ in users
        if u not in admins and u not in professional and (u in live_subs or u in payers)
    }
    free = {u for u, _ in users} - admins - professional - paid
    return {
        "all": {u for u, _ in users},
        "admin": admins,
        "professional": professional,
        "paid": paid,
        "free": free,
        "subscribers": set(live_subs),
    }


@router.get("/overview")
async def overview(_: AdminUser, db: DbSession) -> dict[str, Any]:
    now = datetime.now(UTC)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)
    tiers = await _tier_sets(db, now)
    total_users = len(tiers["all"])

    new_7 = await _count(db, select(func.count()).select_from(User).where(User.created_at >= week))
    new_30 = await _count(
        db, select(func.count()).select_from(User).where(User.created_at >= month)
    )
    active_7 = await _count(
        db, select(func.count()).select_from(User).where(User.last_seen_at >= week)
    )

    def analyses_since(since: datetime) -> Any:
        return (
            select(func.count())
            .select_from(PropertyAnalysis)
            .where(PropertyAnalysis.created_at >= since, PropertyAnalysis.derived_from_id.is_(None))
        )

    free_consumed = await _count(
        db,
        select(func.count())
        .select_from(UsageEvent)
        .where(UsageEvent.kind == "analysis", UsageEvent.credit_source == "free"),
    )
    analyses_30 = await _count(db, analyses_since(month))

    # --- revenue, from verified payments only ------------------------------------
    def revenue(
        since: datetime | None, product: str | None = None, subs: bool | None = None
    ) -> Any:
        stmt = select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
            Payment.status == "succeeded"
        )
        if since is not None:
            stmt = stmt.where(Payment.created_at >= since)
        if product is not None:
            stmt = stmt.where(Payment.product_key == product)
        if subs is True:
            stmt = stmt.where(Payment.subscription_id.is_not(None))
        return stmt

    revenue_all = _money(await db.scalar(revenue(None)))
    revenue_30 = _money(await db.scalar(revenue(month)))
    reports_30 = _money(await db.scalar(revenue(month, product="deep_dive")))
    subs_30 = _money(await db.scalar(revenue(month, subs=True)))
    fees_30 = _money(
        await db.scalar(
            select(func.coalesce(func.sum(Payment.fee_cents), 0)).where(
                Payment.status == "succeeded", Payment.created_at >= month
            )
        )
    )
    fees_estimated = await _count(
        db,
        select(func.count())
        .select_from(Payment)
        .where(Payment.created_at >= month, Payment.fee_is_estimate.is_(True)),
    )
    reports_sold = await _count(
        db,
        select(func.count())
        .select_from(Payment)
        .where(Payment.status == "succeeded", Payment.product_key == "deep_dive"),
    )

    active_subs = (
        await db.scalars(
            select(Subscription).where(
                Subscription.status.in_(accounts.ACTIVE_SUBSCRIPTION_STATUSES)
            )
        )
    ).all()
    mrr = sum(
        s.amount_cents if s.interval == "month" else s.amount_cents // 12 for s in active_subs
    )
    paying = len(tiers["paid"] | tiers["professional"])

    # --- AI / API costs, estimated from the admin's cost assumptions ---------------
    api_rows = (
        await db.execute(
            select(
                ApiUsage.provider,
                func.count(),
                func.coalesce(func.sum(ApiUsage.estimated_cost_millicents), 0),
                func.coalesce(func.sum(ApiUsage.input_tokens), 0),
                func.coalesce(func.sum(ApiUsage.output_tokens), 0),
            )
            .where(ApiUsage.at >= month)
            .group_by(ApiUsage.provider)
        )
    ).all()
    api_cost_30 = sum(Decimal(int(r[2])) for r in api_rows) / Decimal(1000)
    costs = await settings_store.load(db, "costs", CostAssumptions)
    fixed = costs.infrastructure_monthly_cents + costs.other_monthly_cents
    margin = Decimal(revenue_30) - api_cost_30 - Decimal(fees_30) - Decimal(fixed)

    ads = await settings_store.load(db, "ads", AdsConfig)
    ad_users = 0
    if ads.enabled:
        ad_users = (
            (len(tiers["free"]) if ads.show_to_free else 0)
            + (len(tiers["paid"]) if ads.show_to_paid else 0)
            + (len(tiers["professional"]) if ads.show_to_professional else 0)
        )

    def per(value: Decimal | int, count: int) -> float | None:
        return round(float(Decimal(value) / count), 2) if count else None

    return {
        "generated_at": now.isoformat(),
        "users": {
            "total": total_users,
            "new_7d": new_7,
            "new_30d": new_30,
            "active_7d": active_7,
            "free": len(tiers["free"]),
            "paid": len(tiers["paid"]),
            "professional": len(tiers["professional"]),
            "admins": len(tiers["admin"]),
            "subscribers": len(tiers["subscribers"]),
        },
        "usage": {
            "analyses_today": await _count(db, analyses_since(day)),
            "analyses_7d": await _count(db, analyses_since(week)),
            "analyses_30d": analyses_30,
            "free_analyses_consumed": free_consumed,
            "watches": await _count(db, select(func.count()).select_from(PropertyWatch)),
            "comparisons": await _count(db, select(func.count()).select_from(PropertyComparison)),
        },
        "revenue": {
            "currency": "CAD",
            "all_time_cents": revenue_all,
            "last_30d_cents": revenue_30,
            "reports_last_30d_cents": reports_30,
            "subscriptions_last_30d_cents": subs_30,
            "reports_sold": reports_sold,
            "active_subscriptions": len(active_subs),
            "estimated_mrr_cents": mrr,
            "paying_users": paying,
            "conversion_rate": round(paying / total_users, 4) if total_users else None,
            "payments_configured": bool(get_settings().stripe_secret_key),
        },
        "costs": {
            "api_by_provider_30d": [
                {
                    "provider": r[0],
                    "calls": int(r[1]),
                    "estimated_cost_cents": int(r[2]) / 1000,
                    "input_tokens": int(r[3]),
                    "output_tokens": int(r[4]),
                }
                for r in api_rows
            ],
            "api_cost_30d_cents": float(api_cost_30),
            "payment_fees_30d_cents": fees_30,
            "payment_fees_estimated_count": fees_estimated,
            "fixed_monthly_cents": fixed,
            "cost_per_analysis_cents": per(api_cost_30, analyses_30),
            "note": "AI and API costs are estimates from the cost assumptions you set; "
            "payment fees are actual where the provider reported them.",
        },
        "unit_economics": {
            "period": "last 30 days",
            "revenue_cents": revenue_30,
            "ai_api_cost_cents": float(api_cost_30),
            "payment_fees_cents": fees_30,
            "other_costs_cents": fixed,
            "contribution_margin_cents": float(margin),
            "revenue_per_user_cents": per(revenue_30, total_users),
            "cost_per_user_cents": per(api_cost_30 + fees_30 + fixed, total_users),
            "margin_per_user_cents": per(margin, total_users),
            "margin_per_paying_user_cents": per(margin, paying),
        },
        "ads": {
            "enabled": ads.enabled,
            "provider": ads.provider,
            "ad_eligible_users": ad_users,
            "impressions": None,
            "revenue_cents": None,
            "note": "Impressions and ad revenue need a connected ad network's reporting; "
            "none is connected, so they are not shown.",
        },
    }


@router.get("/users")
async def list_users(
    _: AdminUser, db: DbSession, q: str = SEARCH, limit: int = LIMIT
) -> dict[str, Any]:
    stmt = select(User).order_by(User.created_at.desc()).limit(limit)
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q.strip()}%"))
    users = (await db.scalars(stmt)).all()
    now = datetime.now(UTC)
    rows = []
    for user in users:
        ent = await accounts.entitlements_for(db, user, now)
        analyses = await _count(
            db,
            select(func.count())
            .select_from(PropertyAnalysis)
            .where(PropertyAnalysis.user_id == user.id),
        )
        rows.append(
            {
                "id": str(user.id),
                "email": user.email,
                "role": user.role,
                "tier": ent.tier,
                "plan_key": ent.plan_key,
                "free_used": ent.free_used,
                "free_total": ent.free_total,
                "analyses": analyses,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
            }
        )
    return {"users": rows}


class RoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "professional", "admin"]


@router.patch("/users/{user_id}")
async def set_role(user_id: str, body: RoleIn, admin: AdminUser, db: DbSession) -> dict[str, Any]:
    try:
        key = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="User not found.") from exc
    target = await db.get(User, key)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.id == admin.id and body.role != "admin":
        raise HTTPException(status_code=409, detail="You cannot remove your own admin role.")
    previous = target.role
    target.role = body.role
    db.add(
        AuditLog(
            actor_user_id=admin.id,
            action=f"role_change:{previous}->{body.role}",
            entity="user",
            entity_id=target.id,
            at=datetime.now(UTC),
        )
    )
    await db.commit()
    return {"id": str(target.id), "role": target.role}


@router.get("/settings")
async def get_settings_all(_: AdminUser, db: DbSession) -> dict[str, Any]:
    return {key: await settings_store.load_raw(db, key) for key in SETTINGS_MODELS}


@router.put("/settings/{key}")
async def put_setting(
    key: str, value: dict[str, Any], admin: AdminUser, db: DbSession
) -> dict[str, Any]:
    if key not in SETTINGS_MODELS:
        raise HTTPException(status_code=404, detail="Unknown setting.")
    try:
        saved = await settings_store.save(db, key, value, actor=admin.id)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors(include_url=False)
            ],
        ) from exc
    db.add(
        AuditLog(
            actor_user_id=admin.id,
            action=f"settings_update:{key}",
            entity="system_settings",
            at=datetime.now(UTC),
        )
    )
    await db.commit()
    return saved


@router.get("/errors")
async def errors(_: AdminUser, db: DbSession, limit: int = LIMIT) -> dict[str, Any]:
    rows = (await db.scalars(select(ErrorEvent).order_by(ErrorEvent.at.desc()).limit(limit))).all()
    return {
        "errors": [
            {
                "at": e.at.isoformat(),
                "method": e.method,
                "path": e.path,
                "error_class": e.error_class,
                "message": e.message,
            }
            for e in rows
        ]
    }


@router.get("/api-usage")
async def api_usage(_: AdminUser, db: DbSession, limit: int = LIMIT) -> dict[str, Any]:
    rows = (await db.scalars(select(ApiUsage).order_by(ApiUsage.at.desc()).limit(limit))).all()
    return {
        "calls": [
            {
                "at": r.at.isoformat(),
                "provider": r.provider,
                "operation": r.operation,
                "ok": r.ok,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "estimated_cost_cents": r.estimated_cost_millicents / 1000,
                "latency_ms": r.latency_ms,
            }
            for r in rows
        ]
    }


@router.get("/funnel")
async def funnel(_: AdminUser, db: DbSession) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=30)
    rows = (
        await db.execute(
            select(ProductEvent.name, func.count())
            .where(ProductEvent.at >= since)
            .group_by(ProductEvent.name)
        )
    ).all()
    counts = {name: int(n) for name, n in rows}
    order = [
        "landing_viewed",
        "signup_completed",
        "analysis_started",
        "analysis_completed",
        "free_analysis_used",
        "free_limit_reached",
        "deep_dive_viewed",
        "upgrade_clicked",
        "pricing_viewed",
        "deep_dive_checkout_started",
        "subscription_checkout_started",
        "payment_succeeded",
        "property_watch_created",
        "comparison_created",
        "offer_scenarios_run",
        "subscription_viewed",
    ]
    return {
        "period": "last 30 days",
        "events": [{"name": name, "count": counts.get(name, 0)} for name in order],
    }


@router.get("/audit")
async def audit(_: AdminUser, db: DbSession, limit: int = LIMIT) -> dict[str, Any]:
    rows = (
        await db.scalars(
            select(AuditLog)
            .where(or_(AuditLog.action.like("role_%"), AuditLog.action.like("settings_%")))
            .order_by(AuditLog.at.desc())
            .limit(limit)
        )
    ).all()
    return {
        "entries": [
            {
                "at": r.at.isoformat(),
                "actor": str(r.actor_user_id) if r.actor_user_id else None,
                "action": r.action,
                "entity": r.entity,
                "entity_id": str(r.entity_id) if r.entity_id else None,
            }
            for r in rows
        ]
    }
