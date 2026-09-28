"""The payment provider boundary, and Stripe behind it.

Stripe is called over its REST API with ``httpx`` (already a dependency) rather
than through its SDK: four endpoints and a signature check do not justify another
package in a serverless bundle.

Three properties matter more than the code:

* **Hosted checkout only.** Card details go to Stripe's page and never touch this
  server, which keeps the product out of PCI scope.
* **The redirect proves nothing.** Returning to ``/billing/success`` does not grant
  anything; only a signature-verified webhook does.
* **Not configured means not configured.** Without keys, checkout returns a clear
  503 and the UI says payments are not set up — it never pretends a payment worked.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Protocol

import httpx

from app.billing.config import Product
from app.core.config import get_settings

STRIPE_API = "https://api.stripe.com/v1"
SIGNATURE_TOLERANCE_SECONDS = 300


class PaymentsNotConfiguredError(RuntimeError):
    pass


class InvalidSignatureError(ValueError):
    pass


class PaymentProviderError(RuntimeError):
    pass


class PaymentProvider(Protocol):
    name: str

    @property
    def configured(self) -> bool: ...

    async def create_checkout(
        self,
        *,
        product: Product,
        currency: str,
        user_id: str,
        email: str,
        customer_id: str | None,
        analysis_id: str | None,
        success_url: str,
        cancel_url: str,
        percent_off: int | None,
        promo_code: str | None,
    ) -> str: ...

    def verify_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any]: ...

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    async def portal_url(self, customer_id: str, return_url: str) -> str: ...


def verify_stripe_signature(
    payload: bytes, header: str | None, secret: str, *, now: float | None = None
) -> dict[str, Any]:
    """Stripe's scheme: HMAC-SHA256 of ``"{t}.{payload}"``, any ``v1`` may match."""
    if not header or not secret:
        raise InvalidSignatureError("missing signature")
    parts: dict[str, list[str]] = {}
    for item in header.split(","):
        key, _, value = item.strip().partition("=")
        parts.setdefault(key, []).append(value)
    try:
        timestamp = int(parts["t"][0])
    except (KeyError, ValueError) as exc:
        raise InvalidSignatureError("malformed signature header") from exc
    current = time.time() if now is None else now
    if abs(current - timestamp) > SIGNATURE_TOLERANCE_SECONDS:
        raise InvalidSignatureError("signature timestamp outside tolerance")
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in parts.get("v1", [])):
        raise InvalidSignatureError("signature mismatch")
    try:
        event: dict[str, Any] = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise InvalidSignatureError("payload is not JSON") from exc
    return event


class StripeProvider:
    name = "stripe"

    def __init__(self, secret_key: str, webhook_secret: str) -> None:
        self._key = secret_key
        self._webhook_secret = webhook_secret

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def _require(self) -> None:
        if not self._key:
            raise PaymentsNotConfiguredError(
                "Payments are not configured: PDE_STRIPE_SECRET_KEY is not set."
            )

    async def _call(
        self, method: str, path: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self._require()
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.request(
                    method,
                    f"{STRIPE_API}{path}",
                    data=data if method == "POST" else None,
                    params=data if method == "GET" else None,
                    auth=(self._key, ""),
                )
            except httpx.HTTPError as exc:
                raise PaymentProviderError(f"Stripe could not be reached: {exc}") from exc
        body: dict[str, Any] = response.json()
        if response.status_code >= 400:
            message = body.get("error", {}).get("message", "unknown error")
            code = body.get("error", {}).get("code")
            raise PaymentProviderError(f"Stripe refused the request ({code}): {message}")
        return body

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._call("GET", path, params)

    async def _coupon(self, percent_off: int, code: str) -> str:
        coupon_id = f"pde_{code.lower()}_{percent_off}"
        try:
            await self._call("GET", f"/coupons/{coupon_id}")
        except PaymentProviderError:
            await self._call(
                "POST",
                "/coupons",
                {"id": coupon_id, "percent_off": percent_off, "duration": "once", "name": code},
            )
        return coupon_id

    async def create_checkout(
        self,
        *,
        product: Product,
        currency: str,
        user_id: str,
        email: str,
        customer_id: str | None,
        analysis_id: str | None,
        success_url: str,
        cancel_url: str,
        percent_off: int | None,
        promo_code: str | None,
    ) -> str:
        self._require()
        metadata = {
            "user_id": user_id,
            "product_key": product.key,
            "analysis_id": analysis_id or "",
        }
        data: dict[str, Any] = {
            "mode": "subscription" if product.kind == "subscription" else "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": user_id,
            "line_items[0][quantity]": 1,
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][unit_amount]": product.price_cents,
            "line_items[0][price_data][product_data][name]": product.name,
        }
        if product.kind == "subscription":
            data["line_items[0][price_data][recurring][interval]"] = product.interval
            for key, value in metadata.items():
                data[f"subscription_data[metadata][{key}]"] = value
        else:
            for key, value in metadata.items():
                data[f"payment_intent_data[metadata][{key}]"] = value
        for key, value in metadata.items():
            data[f"metadata[{key}]"] = value
        if customer_id:
            data["customer"] = customer_id
        else:
            data["customer_email"] = email
        if percent_off and promo_code:
            data["discounts[0][coupon]"] = await self._coupon(percent_off, promo_code)
            data["metadata[promo_code]"] = promo_code
        session = await self._call("POST", "/checkout/sessions", data)
        url = session.get("url")
        if not isinstance(url, str):
            raise PaymentProviderError("Stripe did not return a checkout URL.")
        return url

    def verify_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        if not self._webhook_secret:
            raise PaymentsNotConfiguredError(
                "Webhooks are not configured: PDE_STRIPE_WEBHOOK_SECRET is not set."
            )
        return verify_stripe_signature(payload, signature, self._webhook_secret)

    async def portal_url(self, customer_id: str, return_url: str) -> str:
        session = await self._call(
            "POST", "/billing_portal/sessions", {"customer": customer_id, "return_url": return_url}
        )
        return str(session["url"])


def payment_provider() -> PaymentProvider:
    settings = get_settings()
    return StripeProvider(settings.stripe_secret_key, settings.stripe_webhook_secret)
