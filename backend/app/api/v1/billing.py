"""Checkout, the signed webhook, the billing portal, and promo codes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.v1.analyses import load_analysis
from app.auth.deps import CurrentUser, DbSession
from app.billing.config import FeatureFlags, PricingConfig, PromotionsConfig
from app.billing.provider import (
    InvalidSignatureError,
    PaymentProviderError,
    PaymentsNotConfiguredError,
    payment_provider,
)
from app.core.config import get_settings
from app.models.account import PromoRedemption, Subscription
from app.services import accounts, billing_service, settings_store

router = APIRouter(prefix="/api/v1")
log = logging.getLogger(__name__)


class CheckoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_key: str = Field(max_length=32)
    analysis_id: str | None = None
    promo_code: str | None = Field(default=None, max_length=32)


class PromoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=3, max_length=32)


@router.post("/billing/checkout")
async def checkout(body: CheckoutIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    pricing = await settings_store.load(db, "pricing", PricingConfig)
    features = await settings_store.load(db, "features", FeatureFlags)
    product = pricing.product(body.product_key)
    if product is None or not product.active:
        raise HTTPException(status_code=404, detail="That product is not available.")
    if product.key == "deep_dive":
        if not features.deep_dive:
            raise HTTPException(status_code=403, detail="Deep Dive reports are not available.")
        if not body.analysis_id:
            raise HTTPException(status_code=422, detail="Choose which analysis to unlock.")
        await load_analysis(db, user, body.analysis_id)

    percent_off: int | None = None
    promo_code: str | None = None
    if body.promo_code:
        promos = await settings_store.load(db, "promotions", PromotionsConfig)
        promo = promos.find(body.promo_code, datetime.now(UTC).date())
        if promo is None or promo.kind != "percent_off":
            raise HTTPException(status_code=422, detail="That promo code is not valid here.")
        if promo.applies_to and product.key not in promo.applies_to:
            raise HTTPException(status_code=422, detail="That code does not apply to this.")
        percent_off, promo_code = promo.value, promo.code

    customer_id = await db.scalar(
        select(Subscription.provider_customer_id)
        .where(Subscription.user_id == user.id, Subscription.provider_customer_id.is_not(None))
        .limit(1)
    )
    settings = get_settings()
    base = settings.public_app_url.rstrip("/")
    provider = payment_provider()
    event = (
        "deep_dive_checkout_started"
        if product.key == "deep_dive"
        else ("subscription_checkout_started")
    )
    accounts.record_event(db, event, user.id, {"product": product.key})
    await db.commit()
    try:
        url = await provider.create_checkout(
            product=product,
            currency=pricing.currency,
            user_id=str(user.id),
            email=user.email,
            customer_id=customer_id,
            analysis_id=body.analysis_id,
            success_url=f"{base}/billing/success?product={product.key}"
            + (f"&analysis={body.analysis_id}" if body.analysis_id else ""),
            cancel_url=f"{base}/billing/cancel?product={product.key}",
            percent_off=percent_off,
            promo_code=promo_code,
        )
    except PaymentsNotConfiguredError as exc:
        raise HTTPException(
            status_code=503,
            detail="Payments are not set up yet, so nothing can be purchased right now. "
            "No charge was made.",
        ) from exc
    except PaymentProviderError as exc:
        log.warning("Checkout failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="The payment provider could not start checkout."
        ) from exc
    return {"url": url}


@router.post("/billing/webhook")
async def webhook(request: Request, db: DbSession) -> dict[str, str]:
    payload = await request.body()
    provider = payment_provider()
    try:
        event = provider.verify_webhook(payload, request.headers.get("stripe-signature"))
    except PaymentsNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail="Webhooks are not configured.") from exc
    except InvalidSignatureError as exc:
        raise HTTPException(status_code=400, detail="Invalid signature.") from exc
    outcome = await billing_service.process_event(db, provider, event)
    return {"status": outcome}


@router.get("/billing/portal")
async def portal(user: CurrentUser, db: DbSession) -> dict[str, str]:
    customer_id = await db.scalar(
        select(Subscription.provider_customer_id)
        .where(Subscription.user_id == user.id, Subscription.provider_customer_id.is_not(None))
        .limit(1)
    )
    if not customer_id:
        raise HTTPException(status_code=404, detail="There is no subscription to manage.")
    try:
        url = await payment_provider().portal_url(
            customer_id, f"{get_settings().public_app_url.rstrip('/')}/account"
        )
    except PaymentsNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail="Payments are not set up yet.") from exc
    except PaymentProviderError as exc:
        raise HTTPException(status_code=502, detail="The billing portal is unavailable.") from exc
    return {"url": url}


@router.get("/billing/summary")
async def billing_summary(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    now = datetime.now(UTC)
    subs = (
        await db.scalars(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.created_at.desc())
        )
    ).all()
    from app.models.account import Payment

    payments = (
        await db.scalars(
            select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc())
        )
    ).all()
    ent = await accounts.entitlements_for(db, user, now)
    return {
        "usage": accounts.usage_summary(ent),
        "payments_configured": bool(get_settings().stripe_secret_key),
        "subscriptions": [
            {
                "product_key": s.product_key,
                "status": s.status,
                "amount_cents": s.amount_cents,
                "currency": s.currency,
                "interval": s.interval,
                "current_period_end": s.current_period_end.isoformat()
                if s.current_period_end
                else None,
                "cancel_at_period_end": s.cancel_at_period_end,
                "manageable": bool(s.provider_customer_id),
            }
            for s in subs
        ],
        "payments": [
            {
                "product_key": p.product_key,
                "amount_cents": p.amount_cents,
                "currency": p.currency,
                "status": p.status,
                "created_at": p.created_at.isoformat(),
                "analysis_id": str(p.analysis_id) if p.analysis_id else None,
            }
            for p in payments
        ],
    }


@router.post("/promo/redeem")
async def redeem(body: PromoIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    promos = await settings_store.load(db, "promotions", PromotionsConfig)
    promo = promos.find(body.code, datetime.now(UTC).date())
    if promo is None:
        raise HTTPException(status_code=404, detail="That code is not valid.")
    if promo.kind != "extra_analyses":
        return {
            "applied": False,
            "message": f"{promo.code} takes {promo.value}% off at checkout — enter it there.",
        }
    already = await db.scalar(
        select(PromoRedemption.id).where(
            PromoRedemption.user_id == user.id, PromoRedemption.code == promo.code
        )
    )
    if already:
        raise HTTPException(status_code=409, detail="You have already used that code.")
    db.add(PromoRedemption(user_id=user.id, code=promo.code, kind=promo.kind, value=promo.value))
    await db.commit()
    ent = await accounts.entitlements_for(db, user)
    return {
        "applied": True,
        "message": f"{promo.value} extra analyses added.",
        "usage": accounts.usage_summary(ent),
    }
