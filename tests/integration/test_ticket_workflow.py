from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from opsdesk.auth.service import AuthPrincipal
from opsdesk.db.base import utc_now
from opsdesk.db.models import User, UserSession
from opsdesk.db.session import get_session_factory
from opsdesk.tickets.models import Ticket, TicketActivity
from opsdesk.tickets.schemas import TicketCreate
from opsdesk.tickets.service import TicketService
from tests.phase3_helpers import (
    GENERAL_CATEGORY_ID,
    ActorFactory,
    command,
    create_ticket,
)

STATUSES = ("open", "in_progress", "waiting_for_user", "resolved", "closed")
ALLOWED = {
    ("open", "in_progress"),
    ("open", "waiting_for_user"),
    ("open", "resolved"),
    ("in_progress", "open"),
    ("in_progress", "waiting_for_user"),
    ("in_progress", "resolved"),
    ("waiting_for_user", "open"),
    ("waiting_for_user", "in_progress"),
    ("waiting_for_user", "resolved"),
    ("resolved", "open"),
    ("resolved", "closed"),
    ("closed", "open"),
}
TRANSITIONS = [
    (current, target) for current in STATUSES for target in STATUSES if current != target
]


@pytest.mark.parametrize(("current", "target"), TRANSITIONS)
def test_complete_agent_transition_matrix(
    actor_factory: ActorFactory, current: str, target: str
) -> None:
    requester = actor_factory("requester@example.com", "user")
    agent = actor_factory("agent@example.com", "agent")
    created = create_ticket(requester)
    ticket_id = uuid.UUID(str(created["id"]))
    with get_session_factory()() as session:
        ticket = session.get(Ticket, ticket_id)
        assert ticket is not None
        ticket.assignee_id = agent.user.id
        ticket.status = current
        ticket.resolved_at = utc_now() if current in {"resolved", "closed"} else None
        ticket.closed_at = utc_now() if current == "closed" else None
        session.commit()

    response = command(
        agent,
        f"/api/v1/tickets/{ticket_id}/status",
        {"status": target, "expected_version": 1},
    )
    expected_status = 200 if (current, target) in ALLOWED else 422
    assert response.status_code == expected_status, response.text
    with get_session_factory()() as session:
        stored = session.get(Ticket, ticket_id)
        assert stored is not None
        if expected_status == 200:
            assert stored.status == target and stored.version == 2
        else:
            assert stored.status == current and stored.version == 1


def test_resolution_close_and_requester_reopen_timestamps(actor_factory: ActorFactory) -> None:
    requester = actor_factory("requester@example.com", "user")
    agent = actor_factory("agent@example.com", "agent")
    created = create_ticket(requester)
    ticket_id = created["id"]
    assert (
        command(
            agent,
            f"/api/v1/tickets/{ticket_id}/assignment",
            {"assignee_id": str(agent.user.id), "expected_version": 1},
        ).status_code
        == 200
    )
    resolved = command(
        agent,
        f"/api/v1/tickets/{ticket_id}/status",
        {"status": "resolved", "expected_version": 2},
    )
    closed = command(
        agent,
        f"/api/v1/tickets/{ticket_id}/status",
        {"status": "closed", "expected_version": 3},
    )
    reopened = command(
        requester,
        f"/api/v1/tickets/{ticket_id}/status",
        {"status": "open", "expected_version": 4},
    )

    assert resolved.status_code == 200 and resolved.json()["resolved_at"] is not None
    assert resolved.json()["closed_at"] is None
    assert closed.status_code == 200 and closed.json()["closed_at"] is not None
    assert closed.json()["resolved_at"] == resolved.json()["resolved_at"]
    assert reopened.status_code == 200
    assert reopened.json()["resolved_at"] is None
    assert reopened.json()["closed_at"] is None


def test_sequence_backed_ticket_numbers_are_unique_under_concurrency(
    actor_factory: ActorFactory,
) -> None:
    requester = actor_factory("requester@example.com", "user")

    def create_concurrently(index: int) -> int:
        with get_session_factory()() as session:
            user = session.get(User, requester.user.id)
            assert user is not None
            principal = AuthPrincipal(
                user=user,
                session=UserSession(
                    user_id=user.id,
                    token_hash=f"{index:064d}",
                    csrf_secret=f"csrf-{index}",
                    expires_at=utc_now() + timedelta(hours=1),
                ),
            )
            ticket = TicketService(session).create(
                principal,
                TicketCreate(
                    title=f"Concurrent request {index}",
                    description="Created in an independent transaction",
                    category_id=GENERAL_CATEGORY_ID,
                ),
                f"concurrent-{index}",
            )
            return ticket.ticket_number

    with ThreadPoolExecutor(max_workers=6) as executor:
        numbers = list(executor.map(create_concurrently, range(6)))

    assert len(numbers) == len(set(numbers)) == 6
    with get_session_factory()() as session:
        assert session.scalar(select(func.count()).select_from(Ticket)) == 6
        assert session.scalar(select(func.count()).select_from(TicketActivity)) == 6
