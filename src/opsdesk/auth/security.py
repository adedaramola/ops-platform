from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from opsdesk.core.config import Settings, get_settings


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def new_csrf_secret() -> str:
    return secrets.token_urlsafe(32)


class PasswordService:
    def __init__(self) -> None:
        self._hasher = PasswordHasher()
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def consume_dummy_verification(self, password: str) -> None:
        self.verify(self._dummy_hash, password)


@lru_cache
def get_password_service() -> PasswordService:
    return PasswordService()


def make_throttle_key(email: str, client_address: str, settings: Settings) -> str:
    value = f"{normalize_email(email)}|{client_address}".encode()
    key = settings.csrf_secret_key.get_secret_value().encode()
    return hmac.new(key, value, hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class CsrfManager:
    settings: Settings

    def issue(self, secret: str | None = None) -> str:
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(18)
        payload = f"{timestamp}.{nonce}"
        signature = self._signature(payload, secret)
        return f"{payload}.{signature}"

    def validate(self, token: str, secret: str | None = None) -> bool:
        try:
            timestamp_text, nonce, supplied_signature = token.split(".", 2)
            timestamp = int(timestamp_text)
        except (TypeError, ValueError):
            return False
        now = int(time.time())
        if timestamp > now + 60 or now - timestamp > self.settings.csrf_max_age_seconds:
            return False
        payload = f"{timestamp_text}.{nonce}"
        return hmac.compare_digest(supplied_signature, self._signature(payload, secret))

    def _signature(self, payload: str, secret: str | None) -> str:
        key_value = secret or self.settings.csrf_secret_key.get_secret_value()
        digest = hmac.new(key_value.encode(), payload.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@lru_cache
def get_csrf_manager() -> CsrfManager:
    return CsrfManager(get_settings())
