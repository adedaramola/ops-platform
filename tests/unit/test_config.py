from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from opsdesk.core.config import Settings


def test_production_rejects_insecure_cookie() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            session_cookie_secure=False,
            csrf_secret_key=SecretStr("a-real-secret"),
        )


def test_production_rejects_default_csrf_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            session_cookie_secure=True,
            csrf_secret_key=SecretStr("development-only-change-me"),
        )


def test_production_rejects_development_seed() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            session_cookie_secure=True,
            csrf_secret_key=SecretStr("a-real-secret"),
            enable_dev_seed=True,
        )
