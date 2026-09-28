"""Turning verified provider events into payments, subscriptions and unlocks.

The only writer of ``payments`` and ``subscriptions``. Every handler is
idempotent twice over: the event id is recorded in ``webhook_events``, and the
rows themselves are unique on the provider's reference.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.config import CostAssumptions, PricingConfig
from app.billing.provider import PaymentProvider, PaymentProviderError
from app.models.account import Payment, Report, Subscription, WebhookEvent
from app.models.analysis import PropertyAnalysis
from app.models.user import User
from app.services import accounts, settings_store

log = logging.getLogger(__name__)


def estimated_fee(amount_cents: int, costs: CostAssumptions) -> int:
    fee = Decimal(amount_cents) * costs.payment_fee_percent / Decimal(100)
    return int(fee.quantize(Decimal("1"), rounding=ROUND_HALF_UP)) + costs.payment_fee_fixed_cents


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _timestamp(value: Any) -> datetime | None:
    return datetime.fromtimestamp(int(value), tz=UTC) if isinstance(value, int | float) else None


async def _actual_fee(
    provider: PaymentProvider, *, payment_intent: str | None, charge: str | None
) -> int | None:
    """The fee Stripe actually charged, from the balance transaction, when reachable."""
    if not provider.configured:
        return None
    try:
        if payment_intent:
            pi = await provider.get(
                f"/payment_intents/{payment_intent}",
                {"expand[]": "latest_charge.balance_transaction"},
            )
            txn = (pi.get("latest_charge") or {}).get("balance_transaction") or {}
        elif charge:
            ch = await provider.get(f"/charges/{charge}", {"expand[]": "balance_transaction"})
            txn = ch.get("balance_transaction") or {}
        else:
            return None
    except PaymentProviderError as exc:
        log.warning("Could not read the processing fee: %s", exc)
        return None
    fee = txn.get("fee") if isinstance(txn, dict) else None
    return int(fee) if isinstance(fee, int) else None


def _subscription_period_end(obj: dict[str, Any]) -> datetime | None:
    end = _timestamp(obj.get("current_period_end"))
    if end is None:
        items = (obj.get("items") or {}).get("data") or []
        if items:
            end = _timestamp(items[0].get("current_period_end"))
    return end


async def process_event(db: AsyncSession, provider: PaymentProvider, event: dict[str, Any]) -> str:
    """Apply one verified event. Returns what was done, for the log and the tests."""
    event_id = str(event.get("id", ""))
    kind = str(event.get("type", ""))
    if not event_id:
        return "ignored: no id"
    if await db.get(WebhookEvent, event_id) is not None:
        return "duplicate"

    obj: dict[str, Any] = (event.get("data") or {}).get("object") or {}
    costs = await settings_store.load(db, "costs", CostAssumptions)
    outcome = "ignored"

    if kind == "checkout.session.completed":
        outcome = await _checkout_completed(db, provider, obj, costs)
    elif kind == "invoice.paid":
        outcome = await _invoice_paid(db, provider, obj, costs)
    elif kind in (
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.created",
    ):
        outcome = await _subscription_changed(db, obj, deleted=kind.endswith("deleted"))

    db.add(WebhookEvent(id=event_id, provider=provider.name, type=kind[:64]))
    await db.commit()
    return outcome


async def _checkout_completed(
    db: AsyncSession, provider: PaymentProvider, obj: dict[str, Any], costs: CostAssumptions
) -> str:
    metadata = obj.get("metadata") or {}
    user_id = _uuid(metadata.get("user_id") or obj.get("client_reference_id"))
    product_key = str(metadata.get("product_key") or "")
    if user_id is None or not product_key or await db.get(User, user_id) is None:
        return "ignored: unknown user or product"

    if obj.get("mode") == "subscription":
        sub_id = obj.get("subscription")
        if not isinstance(sub_id, str):
            return "ignored: no subscription id"
        existing = await db.scalar(
            select(Subscription).where(
                Subscription.provider == provider.name,
                Subscription.provider_subscription_id == sub_id,
            )
        )
        pricing = await settings_store.load(db, "pricing", PricingConfig)
        product = pricing.product(product_key)
        if existing is None:
            db.add(
                Subscription(
                    user_id=user_id,
                    product_key=product_key,
                    status="active",
                    provider=provider.name,
                    provider_customer_id=obj.get("customer"),
                    provider_subscription_id=sub_id,
                    amount_cents=int(
                        obj.get("amount_total") or (product.price_cents if product else 0)
                    ),
                    currency=str(obj.get("currency") or "cad").upper(),
                    interval=product.interval if product and product.interval else "month",
                )
            )
        else:
            existing.status = "active"
        accounts.record_event(db, "payment_succeeded", user_id, {"product": product_key})
        return "subscription started"

    if obj.get("payment_status") != "paid":
        return "ignored: not paid"
    ref = str(obj.get("id"))
    if await db.scalar(
        select(Payment.id).where(Payment.provider == provider.name, Payment.provider_ref == ref)
    ):
        return "duplicate payment"
    amount = int(obj.get("amount_total") or 0)
    fee = await _actual_fee(
        provider,
        payment_intent=obj.get("payment_intent")
        if isinstance(obj.get("payment_intent"), str)
        else None,
        charge=None,
    )
    analysis_id = _uuid(metadata.get("analysis_id"))
    payment = Payment(
        user_id=user_id,
        product_key=product_key,
        analysis_id=analysis_id,
        amount_cents=amount,
        currency=str(obj.get("currency") or "cad").upper(),
        status="succeeded",
        provider=provider.name,
        provider_ref=ref,
        fee_cents=fee if fee is not None else estimated_fee(amount, costs),
        fee_is_estimate=fee is None,
    )
    db.add(payment)
    await db.flush()
    if product_key == "deep_dive" and analysis_id is not None:
        analysis = await db.get(PropertyAnalysis, analysis_id)
        if analysis is not None and analysis.user_id == user_id:
            already = await db.scalar(
                select(Report.id).where(
                    Report.user_id == user_id,
                    Report.analysis_id == analysis_id,
                    Report.kind == "deep_dive",
                )
            )
            if already is None:
                db.add(
                    Report(
                        user_id=user_id,
                        analysis_id=analysis_id,
                        source="purchase",
                        payment_id=payment.id,
                    )
                )
    accounts.record_event(db, "payment_succeeded", user_id, {"product": product_key})
    return "payment recorded"


async def _invoice_paid(
    db: AsyncSession, provider: PaymentProvider, obj: dict[str, Any], costs: CostAssumptions
) -> str:
    sub_id = obj.get("subscription")
    if not isinstance(sub_id, str):
        parent = (obj.get("parent") or {}).get("subscription_details") or {}
        sub_id = parent.get("subscription")
    if not isinstance(sub_id, str):
        return "ignored: invoice without subscription"
    sub = await db.scalar(
        select(Subscription).where(
            Subscription.provider == provider.name,
            Subscription.provider_subscription_id == sub_id,
        )
    )
    if sub is None:
        return "ignored: unknown subscription (checkout event not yet processed)"
    ref = str(obj.get("id"))
    if await db.scalar(
        select(Payment.id).where(Payment.provider == provider.name, Payment.provider_ref == ref)
    ):
        return "duplicate payment"
    amount = int(obj.get("amount_paid") or 0)
    if amount <= 0:
        return "ignored: zero invoice"
    charge = obj.get("charge") if isinstance(obj.get("charge"), str) else None
    fee = await _actual_fee(provider, payment_intent=None, charge=charge)
    db.add(
        Payment(
            user_id=sub.user_id,
            product_key=sub.product_key,
            subscription_id=sub.id,
            amount_cents=amount,
            currency=str(obj.get("currency") or "cad").upper(),
            status="succeeded",
            provider=provider.name,
            provider_ref=ref,
            fee_cents=fee if fee is not None else estimated_fee(amount, costs),
            fee_is_estimate=fee is None,
        )
    )
    sub.status = "active"
    return "invoice recorded"


async def _subscription_changed(db: AsyncSession, obj: dict[str, Any], *, deleted: bool) -> str:
    sub_id = obj.get("id")
    sub = await db.scalar(
        select(Subscription).where(Subscription.provider_subscription_id == sub_id)
    )
    if sub is None:
        metadata = obj.get("metadata") or {}
        user_id = _uuid(metadata.get("user_id"))
        product_key = metadata.get("product_key")
        if user_id is None or not product_key or await db.get(User, user_id) is None:
            return "ignored: unknown subscription"
        sub = Subscription(
            user_id=user_id,
            product_key=str(product_key),
            status=str(obj.get("status") or "incomplete"),
            provider="stripe",
            provider_customer_id=obj.get("customer"),
            provider_subscription_id=str(sub_id),
            amount_cents=0,
        )
        db.add(sub)
    sub.status = "canceled" if deleted else str(obj.get("status") or sub.status)
    sub.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
    end = _subscription_period_end(obj)
    if end is not None:
        sub.current_period_end = end
    return f"subscription {sub.status}"
