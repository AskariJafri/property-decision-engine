"""Webhook signatures, stored-data encryption and passwords."""

import hashlib
import hmac
import json
import time

import pytest

from app.auth.security import csrf_matches, hash_password, verify_password
from app.billing.provider import InvalidSignatureError, verify_stripe_signature
from app.core.config import Settings
from app.core.crypto import EncryptionNotConfiguredError, decrypt_json, encrypt_json

SECRET = "whsec_test"


def signed(payload: bytes, *, secret: str = SECRET, at: int | None = None) -> str:
    t = at if at is not None else int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


class TestStripeSignature:
    payload = json.dumps({"id": "evt_1", "type": "checkout.session.completed"}).encode()

    def test_a_valid_signature_yields_the_event(self):
        assert verify_stripe_signature(self.payload, signed(self.payload), SECRET)["id"] == "evt_1"

    def test_a_tampered_body_is_refused(self):
        header = signed(self.payload)
        with pytest.raises(InvalidSignatureError):
            verify_stripe_signature(self.payload.replace(b"evt_1", b"evt_2"), header, SECRET)

    def test_the_wrong_secret_is_refused(self):
        with pytest.raises(InvalidSignatureError):
            verify_stripe_signature(self.payload, signed(self.payload, secret="other"), SECRET)

    def test_a_replayed_old_event_is_refused(self):
        stale = signed(self.payload, at=int(time.time()) - 3600)
        with pytest.raises(InvalidSignatureError):
            verify_stripe_signature(self.payload, stale, SECRET)

    def test_a_missing_header_is_refused(self):
        with pytest.raises(InvalidSignatureError):
            verify_stripe_signature(self.payload, None, SECRET)


class TestEncryption:
    def test_round_trip_and_opacity(self):
        settings = Settings(environment="local")
        token = encrypt_json({"gross_annual_income_cents": 19_000_000}, settings)
        assert b"19000000" not in token
        assert decrypt_json(token, settings) == {"gross_annual_income_cents": 19_000_000}

    def test_production_refuses_to_run_without_a_key(self):
        with pytest.raises(EncryptionNotConfiguredError):
            encrypt_json({"a": 1}, Settings(environment="production", data_encryption_key=""))

    def test_a_different_key_cannot_read_it(self):
        token = encrypt_json({"a": 1}, Settings(environment="local", session_secret="one"))
        with pytest.raises(ValueError):
            decrypt_json(token, Settings(environment="local", session_secret="two"))


class TestPasswords:
    def test_hash_and_verify(self):
        stored = hash_password("correct horse battery")
        assert stored != "correct horse battery"
        assert verify_password(stored, "correct horse battery")
        assert not verify_password(stored, "wrong")

    def test_an_unknown_account_never_verifies(self):
        assert not verify_password(None, "anything at all")

    def test_csrf_needs_both_halves_and_they_must_match(self):
        assert csrf_matches("abc", "abc")
        assert not csrf_matches("abc", "abd")
        assert not csrf_matches(None, "abc")
        assert not csrf_matches("abc", None)
