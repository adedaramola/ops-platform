from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

os.environ.setdefault("OPS_ENVIRONMENT", "test")
os.environ.setdefault(
    "OPS_DATABASE_URL",
    "postgresql+psycopg://opsdesk:opsdesk_dev_only@localhost:5433/opsdesk_db",
)
os.environ.setdefault("OPS_CSRF_SECRET_KEY", "test-secret-key-with-sufficient-entropy")
os.environ.setdefault("OPS_SESSION_COOKIE_SECURE", "false")
os.environ.setdefault("OPS_AI_ENABLED", "true")
os.environ.setdefault("OPS_AI_DISPATCH_MODE", "memory")
os.environ.setdefault("OPS_AI_INTERNAL_TOKEN", "test-agent-service-token")

from opsdesk.core.config import get_settings
from opsdesk.db.session import clear_database_caches, get_engine
from opsdesk.main import create_app

pytest_plugins = ["tests.phase3_helpers"]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def clean_database(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    if request.node.get_closest_marker("integration") is None:
        yield
        return
    try:
        with get_engine().connect() as connection:
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    except SQLAlchemyError as error:
        pytest.fail(f"PostgreSQL test database is unavailable: {error}")
    if revision != "0004_gateway_usage":
        pytest.fail(f"Expected migration 0004_gateway_usage, found {revision!r}")
    with get_engine().begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE ai_review_events, ai_suggestions, ai_outbox_events, "
                "ai_workflows, ticket_activities, internal_notes, comments, tickets, "
                "audit_events, sessions, login_throttles, users "
                "RESTART IDENTITY CASCADE"
            )
        )
        connection.execute(text("ALTER SEQUENCE ticket_number_seq RESTART WITH 1"))
        connection.execute(
            text("DELETE FROM categories WHERE id <> '00000000-0000-0000-0000-000000000001'")
        )
        connection.execute(
            text(
                "UPDATE categories SET name = 'General', "
                "description = 'General support requests', is_active = true "
                "WHERE id = '00000000-0000-0000-0000-000000000001'"
            )
        )
    yield


@pytest.fixture(scope="session", autouse=True)
def dispose_database_engine() -> Generator[None, None, None]:
    yield
    clear_database_caches()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    with TestClient(create_app(get_settings())) as test_client:
        yield test_client
