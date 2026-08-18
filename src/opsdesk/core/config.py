from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "opsdesk"
    environment: Literal["development", "test", "staging", "production"] = "development"
    version: str = "0.1.0"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://opsdesk:opsdesk_dev_only@localhost:5433/opsdesk_db"
    csrf_secret_key: SecretStr = SecretStr("development-only-change-me")
    session_cookie_name: str = "opsdesk_session"
    csrf_cookie_name: str = "opsdesk_csrf"
    session_cookie_secure: bool = False
    session_absolute_minutes: int = 480
    session_idle_minutes: int = 60
    session_touch_interval_seconds: int = 300
    csrf_max_age_seconds: int = 3600
    login_window_seconds: int = 900
    login_max_failures: int = 5
    login_lock_seconds: int = 900
    enable_dev_seed: bool = False
    seed_user_password: SecretStr | None = None
    seed_agent_password: SecretStr | None = None
    seed_admin_password: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_prefix="OPS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_security_settings(self) -> Settings:
        if self.session_absolute_minutes <= 0 or self.session_idle_minutes <= 0:
            raise ValueError("Session expiration values must be positive")
        if self.environment in {"staging", "production"}:
            if not self.session_cookie_secure:
                raise ValueError("Secure session cookies are required outside development and test")
            if self.enable_dev_seed:
                raise ValueError("Development seed accounts cannot be enabled outside development")
            if self.csrf_secret_key.get_secret_value() == "development-only-change-me":
                raise ValueError("A unique CSRF secret is required outside development and test")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
