from __future__ import annotations

from pydantic import SecretStr

from opsdesk.auth.security import (
    CsrfManager,
    PasswordService,
    hash_session_token,
    make_throttle_key,
    normalize_email,
)
from opsdesk.core.config import Settings


def test_password_hash_and_verify() -> None:
    service = PasswordService()
    password_hash = service.hash("Correct-Horse-99!")

    assert "Correct-Horse-99!" not in password_hash
    assert service.verify(password_hash, "Correct-Horse-99!")
    assert not service.verify(password_hash, "wrong")
    assert not service.verify("not-an-argon-hash", "wrong")


def test_security_helpers_are_normalized_and_deterministic() -> None:
    settings = Settings(csrf_secret_key=SecretStr("test-secret"))

    assert normalize_email("  Person@Example.TEST ") == "person@example.test"
    assert hash_session_token("token") == hash_session_token("token")
    assert hash_session_token("token") != "token"
    assert make_throttle_key("A@example.test", "127.0.0.1", settings) == make_throttle_key(
        "a@example.test", "127.0.0.1", settings
    )


def test_csrf_token_is_signed_and_session_bound() -> None:
    manager = CsrfManager(Settings(csrf_secret_key=SecretStr("global-secret")))
    token = manager.issue("session-secret")

    assert manager.validate(token, "session-secret")
    assert not manager.validate(token, "another-session")
    assert not manager.validate(f"{token}tampered", "session-secret")
