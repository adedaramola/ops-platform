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

from opsdesk.core.config import get_settings
from opsdesk.db.session import clear_database_caches, get_engine
from opsdesk.main import create_app


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
    if revision != "0001_core_auth":
        pytest.fail(f"Expected migration 0001_core_auth, found {revision!r}")
    with get_engine().begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE audit_events, sessions, login_throttles, users "
                "RESTART IDENTITY CASCADE"
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
