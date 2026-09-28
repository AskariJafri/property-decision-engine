"""Accounts: sign up, sign in, sign out, and "who am I".

Deliberately small. Email verification and password reset need an email
provider, which is not configured; both are listed in the roadmap rather than
faked here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, DbSession, OptionalUser
from app.auth.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    hash_password,
    keyed_hash,
    new_token,
    token_hash,
    verify_password,
)
from app.billing.config import AdsConfig, FeatureFlags, PricingConfig
from app.core.config import get_settings
from app.models.account import AuthAttempt, Session
from app.models.user import AuditLog, User
from app.services import accounts, settings_store

router = APIRouter(prefix="/api/v1")

EMAIL_PATTERN = r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,63}$"


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(pattern=EMAIL_PATTERN, max_length=320)
    password: str = Field(min_length=10, max_length=200)


class LoginCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=200)


class ClientEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=64)
    properties: dict[str, str | int | bool] | None = None


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "")


async def _throttle(db: AsyncSession, keys: list[str]) -> None:
    settings = get_settings()
    since = datetime.now(UTC) - timedelta(minutes=15)
    failures = await db.scalar(
        select(func.count())
        .select_from(AuthAttempt)
        .where(
            AuthAttempt.key_hash.in_(keys),
            AuthAttempt.succeeded.is_(False),
            AuthAttempt.at >= since,
        )
    )
    if (failures or 0) >= settings.auth_attempts_per_15_minutes:
        raise HTTPException(
            status_code=429, detail="Too many attempts. Wait a few minutes and try again."
        )


def _record_attempt(db: AsyncSession, keys: list[str], kind: str, ok: bool) -> None:
    for key in keys:
        db.add(AuthAttempt(key_hash=key, kind=kind, succeeded=ok))


def _is_bootstrap_admin(email: str) -> bool:
    listed = get_settings().bootstrap_admin_emails
    return email.lower() in {e.strip().lower() for e in listed.split(",") if e.strip()}


async def _start_session(
    db: AsyncSession, response: Response, user: User, request: Request
) -> None:
    settings = get_settings()
    token = new_token()
    ttl = timedelta(days=settings.session_ttl_days)
    db.add(
        Session(
            id=token_hash(token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + ttl,
            ip_hash=keyed_hash(_client_ip(request)),
        )
    )
    secure = settings.is_deployed
    common: dict[str, Any] = {
        "max_age": int(ttl.total_seconds()),
        "secure": secure,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **common)
    response.set_cookie(CSRF_COOKIE, new_token(), httponly=False, **common)


async def _me(db: AsyncSession, user: User) -> dict[str, Any]:
    ent = await accounts.entitlements_for(db, user)
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "usage": accounts.usage_summary(ent),
    }


@router.post("/auth/signup")
async def signup(
    body: Credentials, request: Request, response: Response, db: DbSession
) -> dict[str, Any]:
    features = await settings_store.load(db, "features", FeatureFlags)
    if not features.signups:
        raise HTTPException(status_code=403, detail="New sign-ups are paused.")
    email = body.email.strip().lower()
    keys = [keyed_hash(f"ip:{_client_ip(request)}")]
    await _throttle(db, keys)

    existing = await db.scalar(select(User).where(func.lower(User.email) == email))
    if existing is not None:
        _record_attempt(db, keys, "signup", False)
        await db.commit()
        raise HTTPException(
            status_code=409, detail="An account with that email already exists. Sign in instead."
        )

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        role="admin" if _is_bootstrap_admin(email) else "user",
    )
    db.add(user)
    await db.flush()
    _record_attempt(db, keys, "signup", True)
    accounts.record_event(db, "signup_completed", user.id)
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="signup",
            entity="user",
            entity_id=user.id,
            at=datetime.now(UTC),
        )
    )
    await _start_session(db, response, user, request)
    await db.commit()
    await db.refresh(user)
    return await _me(db, user)


@router.post("/auth/login")
async def login(
    body: LoginCredentials, request: Request, response: Response, db: DbSession
) -> dict[str, Any]:
    email = body.email.strip().lower()
    keys = [keyed_hash(f"email:{email}"), keyed_hash(f"ip:{_client_ip(request)}")]
    await _throttle(db, keys)

    user = await db.scalar(select(User).where(func.lower(User.email) == email))
    ok = verify_password(user.password_hash if user else None, body.password)
    if user is None or not ok or user.deleted_at is not None:
        _record_attempt(db, keys, "login", False)
        await db.commit()
        raise HTTPException(status_code=401, detail="That email and password do not match.")

    if _is_bootstrap_admin(email) and user.role != "admin":
        user.role = "admin"
        db.add(
            AuditLog(
                actor_user_id=user.id,
                action="role_bootstrap_admin",
                entity="user",
                entity_id=user.id,
                at=datetime.now(UTC),
            )
        )
    _record_attempt(db, keys, "login", True)
    await _start_session(db, response, user, request)
    await db.commit()
    return await _me(db, user)


@router.post("/auth/logout")
async def logout(request: Request, response: Response, db: DbSession) -> dict[str, bool]:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await db.execute(delete(Session).where(Session.id == token_hash(token)))
        await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return await _me(db, user)


@router.get("/config/public")
async def public_config(db: DbSession) -> dict[str, Any]:
    """What any visitor may know: prices, which features are on, and ad placement."""
    pricing = await settings_store.load(db, "pricing", PricingConfig)
    features = await settings_store.load(db, "features", FeatureFlags)
    ads = await settings_store.load(db, "ads", AdsConfig)
    return {
        "currency": pricing.currency,
        "free_analyses": pricing.free_analyses,
        "products": [p.model_dump(mode="json") for p in pricing.products if p.active],
        "features": features.model_dump(mode="json"),
        "ads": {
            "enabled": ads.enabled,
            "provider": ads.provider,
            "adsense_client": ads.adsense_client,
            "slots": ads.slots,
        },
        "payments_configured": bool(get_settings().stripe_secret_key),
    }


@router.post("/events", status_code=202)
async def client_event(body: ClientEvent, user: OptionalUser, db: DbSession) -> dict[str, bool]:
    """Funnel events from the browser. Whitelisted names; anything else is ignored."""
    if body.name not in accounts.CLIENT_EVENTS:
        return {"accepted": False}
    accounts.record_event(db, body.name, user.id if user else None, body.properties)
    await db.commit()
    return {"accepted": True}
