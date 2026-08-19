from __future__ import annotations

import pytest
from pydantic import ValidationError

from opsdesk.core.config import Settings
from opsdesk.main import create_app


def test_controlled_failure_routes_are_absent_by_default() -> None:
    paths = {
        route.path
        for route in create_app(Settings(environment="test")).routes
        if hasattr(route, "path")
    }
    assert "/api/v1/development/failures/slow" not in paths
    assert "/api/v1/development/failures/error" not in paths


def test_controlled_failures_are_development_only() -> None:
    with pytest.raises(ValidationError, match="Controlled failures"):
        Settings(
            environment="production",
            session_cookie_secure=True,
            csrf_secret_key="unique-production-secret",
            enable_controlled_failures=True,
        )
    with pytest.raises(ValidationError, match="Controlled failures"):
        Settings(environment="test", enable_controlled_failures=True)


def test_demo_traffic_cannot_be_enabled_in_production() -> None:
    with pytest.raises(ValidationError, match="Demo traffic"):
        Settings(
            environment="production",
            session_cookie_secure=True,
            csrf_secret_key="unique-production-secret",
            traffic_enabled=True,
        )
