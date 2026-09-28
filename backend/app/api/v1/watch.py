"""Property Watch: save a property, record what changes, see how it moves your numbers.

A price change re-runs the full analysis at the new price — a new, immutable
analysis row linked to the one it revises — and the response shows the
difference. That recalculation is part of the watch, so it consumes no credit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.analyses import load_analysis, stored_request, stored_result
from app.api.v1.routes import (
    RULES,
    SERVICE,
    _analysis_row,
    _resolve_location,
)
from app.auth.deps import CurrentUser, DbSession
from app.billing.config import FeatureFlags
from app.core.config import get_settings
from app.engines.scoring.contracts import SCORING_MODEL_VERSION
from app.models.account import PropertyWatch, PropertyWatchEvent, UsageEvent
from app.models.analysis import PropertyAnalysis
from app.models.user import User
from app.providers.watch import PROVIDERS, automated_providers
from app.services import accounts, settings_store
from app.services.analysis_service import inputs_hash_for

router = APIRouter(prefix="/api/v1")

LISTING_STATUSES = (
    "for_sale",
    "conditional",
    "sold",
    "terminated",
    "expired",
    "relisted",
    "unknown",
)


class WatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: str


class WatchUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_cents: int | None = Field(default=None, gt=0, le=100_000_000_00)
    listing_status: (
        Literal["for_sale", "conditional", "sold", "terminated", "expired", "relisted", "unknown"]
        | None
    ) = None
    days_on_market: int | None = Field(default=None, ge=0, le=3650)
    note: str | None = Field(default=None, max_length=500)


async def _load_watch(db: AsyncSession, user: User, watch_id: str) -> PropertyWatch:
    try:
        key = uuid.UUID(watch_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Watch not found.") from exc
    watch = await db.get(PropertyWatch, key)
    if watch is None or watch.user_id != user.id:
        raise HTTPException(status_code=404, detail="Watch not found.")
    return watch


def _money(result: dict[str, Any]) -> dict[str, int | None]:
    money = result["money"]
    payment = next(
        (
            line["amount_cents"]
            for line in result.get("monthly_breakdown", [])
            if line["key"] == "mortgage_payment"
        ),
        None,
    )
    return {
        "purchase_price_cents": money["purchase_price_cents"],
        "monthly_payment_cents": payment,
        "monthly_ownership_cost_cents": money["monthly_ownership_cost_cents"],
        "closing_costs_cents": money["closing_costs_cents"],
        "cash_required_cents": money["cash_required_cents"],
        "buy_score": result.get("buy_score"),
    }


def _impact(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    a, b = _money(before), _money(after)
    labels = {
        "purchase_price_cents": "Price",
        "monthly_payment_cents": "Mortgage payment",
        "monthly_ownership_cost_cents": "Monthly carrying cost",
        "closing_costs_cents": "Closing costs",
        "cash_required_cents": "Cash required upfront",
        "buy_score": "Buy Score",
    }
    rows = []
    for key, label in labels.items():
        old, new = a[key], b[key]
        rows.append(
            {
                "key": key,
                "label": label,
                "before": old,
                "after": new,
                "change": (new - old) if old is not None and new is not None else None,
            }
        )
    return rows


async def _serialise(db: AsyncSession, watch: PropertyWatch) -> dict[str, Any]:
    events = (
        await db.scalars(
            select(PropertyWatchEvent)
            .where(PropertyWatchEvent.watch_id == watch.id)
            .order_by(PropertyWatchEvent.created_at.desc())
            .limit(50)
        )
    ).all()
    return {
        "id": str(watch.id),
        "title": watch.title,
        "status": watch.status,
        "listing_status": watch.listing_status,
        "last_price_cents": watch.last_price_cents,
        "days_on_market": watch.days_on_market,
        "provider": watch.provider_key,
        "original_analysis_id": str(watch.original_analysis_id),
        "current_analysis_id": str(watch.current_analysis_id),
        "created_at": watch.created_at.isoformat() if watch.created_at else None,
        "events": [
            {
                "id": str(e.id),
                "field": e.field,
                "old_value": e.old_value,
                "new_value": e.new_value,
                "source": e.source,
                "note": e.note,
                "analysis_id": str(e.analysis_id) if e.analysis_id else None,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    }


@router.get("/watches")
async def list_watches(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    ent = await accounts.entitlements_for(db, user)
    watches = (
        await db.scalars(
            select(PropertyWatch)
            .where(PropertyWatch.user_id == user.id)
            .order_by(PropertyWatch.created_at.desc())
        )
    ).all()
    return {
        "watches": [await _serialise(db, w) for w in watches],
        "watch_limit": ent.watch_limit,
        "providers": [
            {"key": p.key, "automated": p.automated, "description": p.description}
            for p in PROVIDERS.values()
        ],
        "automatic_monitoring": bool(automated_providers()),
    }


@router.post("/watches", status_code=201)
async def create_watch(body: WatchIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    features = await settings_store.load(db, "features", FeatureFlags)
    if not features.property_watch:
        raise HTTPException(status_code=403, detail="Property Watch is not available.")
    row = await load_analysis(db, user, body.analysis_id)
    ent = await accounts.entitlements_for(db, user)
    existing = await db.scalar(
        select(func.count()).select_from(PropertyWatch).where(PropertyWatch.user_id == user.id)
    )
    if ent.watch_limit is not None and (existing or 0) >= ent.watch_limit:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "watch_locked" if ent.watch_limit == 0 else "watch_limit_reached",
                "message": "Property Watch is part of the Property Watch and Professional plans."
                if ent.watch_limit == 0
                else f"Your plan includes {ent.watch_limit} watched properties.",
                "usage": accounts.usage_summary(ent),
            },
        )
    duplicate = await db.scalar(
        select(PropertyWatch).where(
            PropertyWatch.user_id == user.id, PropertyWatch.current_analysis_id == row.id
        )
    )
    if duplicate is not None:
        return await _serialise(db, duplicate)

    watch = PropertyWatch(
        user_id=user.id,
        original_analysis_id=row.id,
        current_analysis_id=row.id,
        title=row.title or "Property",
        last_price_cents=row.purchase_price_cents or 0,
        listing_status="for_sale",
        provider_key="manual",
    )
    db.add(watch)
    accounts.record_event(db, "property_watch_created", user.id)
    await db.commit()
    await db.refresh(watch)
    return await _serialise(db, watch)


@router.post("/watches/{watch_id}/updates")
async def update_watch(
    watch_id: str, body: WatchUpdateIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    watch = await _load_watch(db, user, watch_id)
    if body.price_cents is None and body.listing_status is None and body.days_on_market is None:
        raise HTTPException(status_code=422, detail="Enter a new price, status or days on market.")

    impact: list[dict[str, Any]] | None = None
    new_analysis_id: uuid.UUID | None = None
    if body.price_cents is not None and body.price_cents != watch.last_price_cents:
        current = await load_analysis(db, user, str(watch.current_analysis_id))
        request = stored_request(current)
        request.property.purchase_price_cents = body.price_cents
        now = datetime.now(UTC)
        try:
            analysis = SERVICE.analyze(
                request, as_of=now.date(), location=await _resolve_location(request)
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"At the new price the analysis cannot run: {exc}",
            ) from exc
        analysis.explanation_unavailable_reason = (
            "Recalculated after a price change; explanations are generated only for new analyses."
        )
        fingerprint = inputs_hash_for(request, RULES.label, SCORING_MODEL_VERSION)
        new_row: PropertyAnalysis = _analysis_row(
            user, request, analysis, fingerprint, now, "none", derived_from=current.id
        )
        db.add(new_row)
        await db.flush()
        db.add(
            UsageEvent(user_id=user.id, analysis_id=new_row.id, kind="watch_recalculation", at=now)
        )
        db.add(
            PropertyWatchEvent(
                watch_id=watch.id,
                field="price",
                old_value=str(watch.last_price_cents),
                new_value=str(body.price_cents),
                source="user",
                note=body.note,
                analysis_id=new_row.id,
            )
        )
        impact = _impact(stored_result(current), analysis.model_dump(mode="json"))
        watch.last_price_cents = body.price_cents
        watch.current_analysis_id = new_row.id
        new_analysis_id = new_row.id

    if body.listing_status is not None and body.listing_status != watch.listing_status:
        db.add(
            PropertyWatchEvent(
                watch_id=watch.id,
                field="listing_status",
                old_value=watch.listing_status,
                new_value=body.listing_status,
                source="user",
                note=body.note if body.price_cents is None else None,
            )
        )
        watch.listing_status = body.listing_status
    if body.days_on_market is not None and body.days_on_market != watch.days_on_market:
        db.add(
            PropertyWatchEvent(
                watch_id=watch.id,
                field="days_on_market",
                old_value=str(watch.days_on_market) if watch.days_on_market is not None else None,
                new_value=str(body.days_on_market),
                source="user",
            )
        )
        watch.days_on_market = body.days_on_market

    watch.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(watch)
    return {
        "watch": await _serialise(db, watch),
        "impact": impact,
        "new_analysis_id": str(new_analysis_id) if new_analysis_id else None,
    }


@router.delete("/watches/{watch_id}")
async def delete_watch(watch_id: str, user: CurrentUser, db: DbSession) -> dict[str, bool]:
    watch = await _load_watch(db, user, watch_id)
    await db.delete(watch)
    await db.commit()
    return {"deleted": True}


@router.post("/internal/watch/refresh")
async def refresh_watches(
    db: DbSession, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    """For a scheduler. Checks watches whose provider is automated — none today."""
    secret = get_settings().cron_secret
    if not secret or authorization != f"Bearer {secret}":
        raise HTTPException(status_code=401, detail="Not authorised.")
    providers = {p.key: p for p in automated_providers()}
    if not providers:
        return {
            "checked": 0,
            "note": "No automated listing provider is configured; watches are updated by "
            "their owners.",
        }
    watches = (
        await db.scalars(
            select(PropertyWatch).where(
                PropertyWatch.status == "active",
                PropertyWatch.provider_key.in_(list(providers)),
            )
        )
    ).all()
    # A future provider records changes here exactly as a manual update does.
    return {"checked": len(watches)}
