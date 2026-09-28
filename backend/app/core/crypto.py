"""The cipher behind the ``encrypted()`` columns.

``models/base.py`` has promised since Phase C that a household's income, debts and
savings are opaque bytes at rest. This is the other half of that promise: Fernet
(AES-128-CBC with an HMAC), keyed from the environment, applied in the service
layer so the database never holds a readable value.
"""

from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings, get_settings


class EncryptionNotConfiguredError(RuntimeError):
    """A deployed environment with no key. Refused rather than weakened."""


def _key_for(settings: Settings) -> bytes:
    if settings.data_encryption_key:
        return settings.data_encryption_key.encode()
    if settings.is_deployed:
        raise EncryptionNotConfiguredError(
            "PDE_DATA_ENCRYPTION_KEY is not set. Stored analyses hold a household's "
            "finances and are never written unencrypted in a deployed environment."
        )
    # Local and CI only: a key derived from the (non-secret) dev session secret, so a
    # fresh checkout works. Never reached in staging or production.
    digest = hashlib.sha256(f"pde-dev-key:{settings.session_secret}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache
def _fernet(key: bytes) -> Fernet:
    return Fernet(key)


def encrypt_json(value: Any, settings: Settings | None = None) -> bytes:
    fernet = _fernet(_key_for(settings or get_settings()))
    return fernet.encrypt(json.dumps(value, separators=(",", ":")).encode())


def decrypt_json(token: bytes, settings: Settings | None = None) -> Any:
    fernet = _fernet(_key_for(settings or get_settings()))
    try:
        return json.loads(fernet.decrypt(token))
    except InvalidToken as exc:
        raise ValueError("stored data could not be decrypted with the configured key") from exc
