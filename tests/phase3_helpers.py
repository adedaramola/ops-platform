from __future__ import annotations

import uuid
from collections.abc import Callable, Generator
from contextlib import ExitStack
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from opsdesk.auth.security import get_password_service
from opsdesk.core.config import get_settings
from opsdesk.db.models import User
from opsdesk.db.session import get_session_factory
from opsdesk.main import create_app
from tests.helpers import PASSWORD, csrf, login

GENERAL_CATEGORY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@dataclass(frozen=True, slots=True)
class Actor:
    client: TestClient
    user: User


ActorFactory = Callable[[str, str], Actor]


@pytest.fixture
def actor_factory() -> Generator[ActorFactory, None, None]:
    with ExitStack() as stack:

        def make(email: str, role: str = "user") -> Actor:
            with get_session_factory()() as session:
                user = User(
                    email=email,
                    password_hash=get_password_service().hash(PASSWORD),
                    role_key=role,
                    is_active=True,
                )
                session.add(user)
                session.commit()
                session.refresh(user)
                session.expunge(user)
            client = stack.enter_context(TestClient(create_app(get_settings())))
            response = login(client, email=email)
            assert response.status_code == 200
            return Actor(client=client, user=user)

        yield make


def create_ticket(
    actor: Actor,
    *,
    title: str = "Printer is unavailable",
    description: str = "The third floor printer stopped responding.",
    category_id: uuid.UUID = GENERAL_CATEGORY_ID,
    priority: str = "medium",
) -> dict[str, object]:
    token = csrf(actor.client)
    response = actor.client.post(
        "/api/v1/tickets",
        headers={"X-CSRF-Token": token},
        json={
            "title": title,
            "description": description,
            "category_id": str(category_id),
            "priority": priority,
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def command(
    actor: Actor,
    path: str,
    payload: dict[str, object],
) -> object:
    token = csrf(actor.client)
    return actor.client.post(path, headers={"X-CSRF-Token": token}, json=payload)
