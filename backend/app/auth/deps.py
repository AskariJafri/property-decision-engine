"""Request dependencies: who is asking, and are they allowed.

The role is read from the ``users`` row on every request. Nothing the browser
sends — a header, a body field, a cookie other than the opaque session token —
can make a request an admin's.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, csrf_matches, token_hash
from app.db.session import get_session
from app.models.account import Session
from app.models.user import User

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def optional_user(request: Request, db: DbSession) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    now = datetime.now(UTC)
    row = (
        await db.execute(
            select(Session, User)
            .join(User, User.id == Session.user_id)
            .where(Session.id == token_hash(token))
        )
    ).first()
    if row is None:
        return None
    session: Session = row[0]
    user: User = row[1]
    expires = (
        session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=UTC)
    )
    if expires <= now or user.deleted_at is not None:
        return None

    # Cross-site request forgery: a signed-in browser's unsafe request must echo
    # the readable CSRF cookie in a header, which another origin cannot do.
    if request.method in UNSAFE_METHODS and not csrf_matches(
        request.cookies.get(CSRF_COOKIE), request.headers.get(CSRF_HEADER)
    ):
        raise HTTPException(status_code=403, detail="Missing or invalid CSRF token.")

    # "Active users" needs a last-seen time; once an hour is plenty and keeps
    # reads from becoming writes.
    last = user.last_seen_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    if last is None or now - last > timedelta(hours=1):
        user.last_seen_at = now
        await db.commit()
    return user


async def current_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user


async def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admins only.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]
AdminUser = Annotated[User, Depends(require_admin)]
