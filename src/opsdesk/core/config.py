from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "opsdesk"
    environment: Literal["development", "test", "staging", "production"] = "development"
    version: str = "0.3.0"
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
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4318/v1/traces"
    otel_export_timeout_seconds: float = 2.0
    otel_sample_ratio: float = 1.0
    enable_controlled_failures: bool = False
    controlled_failure_max_delay_ms: int = 2_000
    traffic_enabled: bool = False
    traffic_base_url: str = "http://localhost:8000"
    traffic_rate_per_second: float = 0.2
    traffic_concurrency: int = 2
    traffic_duration_seconds: float = 60.0
    traffic_request_timeout_seconds: float = 5.0
    traffic_controlled_outcomes: bool = True
    traffic_controlled_failures: bool = False

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
        if self.enable_controlled_failures and self.environment != "development":
            raise ValueError("Controlled failures can only be enabled in development")
        if self.traffic_enabled and self.environment == "production":
            raise ValueError("Demo traffic cannot be enabled in production")
        if not 0.0 <= self.otel_sample_ratio <= 1.0:
            raise ValueError("OpenTelemetry sample ratio must be between 0 and 1")
        if self.otel_export_timeout_seconds <= 0:
            raise ValueError("OpenTelemetry export timeout must be positive")
        if not 1 <= self.controlled_failure_max_delay_ms <= 10_000:
            raise ValueError("Controlled failure delay limit must be between 1 and 10000 ms")
        if not 0.01 <= self.traffic_rate_per_second <= 100:
            raise ValueError("Traffic rate must be between 0.01 and 100 scenarios per second")
        if not 1 <= self.traffic_concurrency <= 50:
            raise ValueError("Traffic concurrency must be between 1 and 50")
        if not 0.1 <= self.traffic_duration_seconds <= 86_400:
            raise ValueError("Traffic duration must be between 0.1 and 86400 seconds")
        if self.traffic_request_timeout_seconds <= 0:
            raise ValueError("Traffic request timeout must be positive")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
