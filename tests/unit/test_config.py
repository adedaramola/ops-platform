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


def test_production_rejects_development_database_credentials() -> None:
    with pytest.raises(ValidationError, match="Development database credentials"):
        Settings(
            environment="production",
            database_url=("postgresql+psycopg://opsdesk:opsdesk_dev_only@database:5432/opsdesk_db"),
            session_cookie_secure=True,
            csrf_secret_key=SecretStr("a-real-secret"),
        )


def test_production_rejects_encoded_development_database_credentials() -> None:
    with pytest.raises(ValidationError, match="Development database credentials"):
        Settings(
            environment="production",
            database_url=(
                "postgresql+psycopg://opsdesk:opsdesk%5Fdev%5Fonly@database:5432/opsdesk_db"
            ),
            session_cookie_secure=True,
            csrf_secret_key=SecretStr("a-real-secret"),
        )


def test_production_requires_postgresql_psycopg_url() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL with the psycopg driver"):
        Settings(
            environment="production",
            database_url="sqlite:///opsdesk.db",
            session_cookie_secure=True,
            csrf_secret_key=SecretStr("a-real-secret"),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("database_pool_size", 0, "Database pool size"),
        ("database_max_overflow", -1, "Database max overflow"),
        ("database_pool_timeout_seconds", 0, "Database pool timeout"),
        ("database_pool_recycle_seconds", 29, "Database pool recycle"),
        ("database_connect_timeout_seconds", 0, "Database connect timeout"),
    ],
)
def test_database_pool_settings_are_bounded(field: str, value: int, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(**{field: value})


def test_database_url_is_redacted_from_settings_representation() -> None:
    settings = Settings(database_url="postgresql+psycopg://opsdesk:do-not-print@database/opsdesk")

    assert "do-not-print" not in repr(settings)
    assert settings.database_url.get_secret_value().endswith("@database/opsdesk")
