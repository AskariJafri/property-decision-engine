"""Password hashing, session tokens, and the hashes that stand in for identifiers.

* Passwords: argon2id via ``argon2-cffi``, the library's recommended parameters.
* Sessions: a 256-bit random token in an httpOnly cookie; only its sha256 is stored.
* CSRF: double-submit. A second, readable cookie holds a random value the page
  echoes in ``X-CSRF-Token``; a cross-site form cannot read it, so cannot echo it.
* Throttling keys and IPs are stored as keyed hashes, never raw.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

SESSION_COOKIE = "pde_session"
CSRF_COOKIE = "pde_csrf"
CSRF_HEADER = "X-CSRF-Token"

_hasher = PasswordHasher()

#: Compared against when the email is unknown, so a missing account and a wrong
#: password take the same time and cannot be told apart.
_DUMMY_HASH = _hasher.hash("not-a-real-password-used-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and bool(password_hash)
    except (VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def keyed_hash(value: str) -> str:
    """A stable, non-reversible stand-in for an email or IP address."""
    key = get_settings().session_secret.encode()
    return hmac.new(key, value.strip().lower().encode(), hashlib.sha256).hexdigest()


def csrf_matches(cookie: str | None, header: str | None) -> bool:
    return bool(cookie) and bool(header) and hmac.compare_digest(cookie or "", header or "")
