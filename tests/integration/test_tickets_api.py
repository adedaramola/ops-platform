from __future__ import annotations

import json

import pytest
import structlog
from sqlalchemy import func, select

from opsdesk.core.config import get_settings
from opsdesk.db.models import AuditEvent
from opsdesk.db.session import get_session_factory
from opsdesk.observability.logging import configure_logging
from opsdesk.tickets.models import TicketActivity
from tests.helpers import csrf
from tests.phase3_helpers import ActorFactory, command, create_ticket


def test_ticket_isolation_search_and_stable_pagination(actor_factory: ActorFactory) -> None:
    first = actor_factory("first@example.com", "user")
    second = actor_factory("second@example.com", "user")
    agent = actor_factory("agent@example.com", "agent")
    first_ticket = create_ticket(first, title="VPN connection fails")
    create_ticket(first, title="Laptop screen flickers")
    other_ticket = create_ticket(second, title="Private payroll issue")

    own = first.client.get("/api/v1/tickets", params={"page_size": 1})
    second_page = first.client.get("/api/v1/tickets", params={"page": 2, "page_size": 1})
    hidden = first.client.get(f"/api/v1/tickets/{other_ticket['id']}")
    search = first.client.get("/api/v1/tickets", params={"query": "payroll"})
    forbidden_filter = first.client.get(
        "/api/v1/tickets", params={"requester_id": str(second.user.id)}
    )
    staff_view = agent.client.get("/api/v1/tickets")

    assert own.status_code == 200 and own.json()["total"] == 2
    assert second_page.status_code == 200 and len(second_page.json()["items"]) == 1
    assert own.json()["items"][0]["id"] != second_page.json()["items"][0]["id"]
    assert hidden.status_code == 404
    assert search.json()["total"] == 0
    assert forbidden_filter.status_code == 403
    assert staff_view.json()["total"] == 3
    assert first.client.get(f"/api/v1/tickets/{first_ticket['id']}").status_code == 200


def test_authorized_filters_ticket_number_and_role_dashboards(
    actor_factory: ActorFactory,
) -> None:
    requester = actor_factory("requester@example.com", "user")
    other_requester = actor_factory("other-requester@example.com", "user")
    agent = actor_factory("agent@example.com", "agent")
    first = create_ticket(requester, title="VPN unavailable", priority="high")
    create_ticket(requester, title="Keyboard replacement", priority="low")
    create_ticket(other_requester, title="Payroll access", priority="high")

    claim = command(
        agent,
        f"/api/v1/tickets/{first['id']}/assignment",
        {"assignee_id": str(agent.user.id), "expected_version": 1},
    )
    assert claim.status_code == 200
    progress = command(
        agent,
        f"/api/v1/tickets/{first['id']}/status",
        {"status": "in_progress", "expected_version": 2},
    )
    assert progress.status_code == 200

    by_number = requester.client.get("/api/v1/tickets", params={"query": first["display_number"]})
    by_status = requester.client.get("/api/v1/tickets", params={"status": "in_progress"})
    by_priority = requester.client.get("/api/v1/tickets", params={"priority": "high"})
    by_category = requester.client.get(
        "/api/v1/tickets", params={"category_id": first["category_id"]}
    )
    assigned = agent.client.get("/api/v1/tickets", params={"assignee_id": str(agent.user.id)})
    unassigned = agent.client.get("/api/v1/tickets", params={"unassigned": True})
    user_dashboard = requester.client.get("/api/v1/dashboard")
    agent_dashboard = agent.client.get("/api/v1/dashboard")

    assert by_number.json()["total"] == 1
    assert by_number.json()["items"][0]["id"] == first["id"]
    assert by_status.json()["total"] == 1
    assert by_priority.json()["total"] == 1
    assert by_category.json()["total"] == 2
    assert assigned.json()["total"] == 1
    assert unassigned.json()["total"] == 2
    assert user_dashboard.json() == {
        "role": "user",
        "status_counts": {"in_progress": 1, "open": 1},
        "total_visible": 2,
        "unassigned": 0,
        "assigned_to_me": 0,
    }
    assert agent_dashboard.json() == {
        "role": "agent",
        "status_counts": {"in_progress": 1, "open": 2},
        "total_visible": 3,
        "unassigned": 2,
        "assigned_to_me": 1,
    }


def test_assignment_reassignment_and_optimistic_conflict(actor_factory: ActorFactory) -> None:
    requester = actor_factory("requester@example.com", "user")
    first_agent = actor_factory("first-agent@example.com", "agent")
    second_agent = actor_factory("second-agent@example.com", "agent")
    admin = actor_factory("admin@example.com", "admin")
    ticket = create_ticket(requester)
    ticket_id = ticket["id"]

    claim = command(
        first_agent,
        f"/api/v1/tickets/{ticket_id}/assignment",
        {"assignee_id": str(first_agent.user.id), "expected_version": 1},
    )
    assert isinstance(claim, object) and claim.status_code == 200
    assert claim.json()["assignee_id"] == str(first_agent.user.id)

    other_agent_change = command(
        second_agent,
        f"/api/v1/tickets/{ticket_id}/priority",
        {"priority": "high", "expected_version": 2},
    )
    agent_reassign = command(
        first_agent,
        f"/api/v1/tickets/{ticket_id}/assignment",
        {"assignee_id": str(second_agent.user.id), "expected_version": 2},
    )
    admin_reassign = command(
        admin,
        f"/api/v1/tickets/{ticket_id}/assignment",
        {"assignee_id": str(second_agent.user.id), "expected_version": 2},
    )
    stale = command(
        admin,
        f"/api/v1/tickets/{ticket_id}/priority",
        {"priority": "critical", "expected_version": 2},
    )

    assert other_agent_change.status_code == 403
    assert agent_reassign.status_code == 403
    assert admin_reassign.status_code == 200
    assert stale.status_code == 409
    with get_session_factory()() as session:
        stale_activity = session.scalar(
            select(func.count())
            .select_from(TicketActivity)
            .where(TicketActivity.event_type == "ticket.priority_changed")
        )
        stale_audit = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "ticket.priority_changed")
        )
        assert stale_activity == 0
        assert stale_audit == 0


def test_comments_and_internal_notes_have_separate_privacy_boundaries(
    actor_factory: ActorFactory,
) -> None:
    requester = actor_factory("requester@example.com", "user")
    agent = actor_factory("agent@example.com", "agent")
    ticket = create_ticket(requester, title="Database access request")
    ticket_id = ticket["id"]

    comment_token = csrf(requester.client)
    comment = requester.client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers={"X-CSRF-Token": comment_token},
        json={"body": "Public progress update"},
    )
    note_token = csrf(agent.client)
    note = agent.client.post(
        f"/api/v1/tickets/{ticket_id}/internal-notes",
        headers={"X-CSRF-Token": note_token},
        json={"body": "PRIVATE-NOTE-MARKER do not disclose"},
    )

    detail = requester.client.get(f"/api/v1/tickets/{ticket_id}")
    activity = requester.client.get(f"/api/v1/tickets/{ticket_id}/activity")
    denied_notes = requester.client.get(f"/api/v1/tickets/{ticket_id}/internal-notes")
    search = requester.client.get("/api/v1/tickets", params={"query": "PRIVATE-NOTE-MARKER"})
    staff_notes = agent.client.get(f"/api/v1/tickets/{ticket_id}/internal-notes")

    assert comment.status_code == 201
    assert note.status_code == 201
    assert "Public progress update" in detail.text
    assert "PRIVATE-NOTE-MARKER" not in detail.text
    assert "internal_note.created" not in activity.text
    assert "PRIVATE-NOTE-MARKER" not in activity.text
    assert denied_notes.status_code == 403
    assert "PRIVATE-NOTE-MARKER" not in denied_notes.text
    assert search.json()["total"] == 0
    assert "PRIVATE-NOTE-MARKER" not in search.text
    assert staff_notes.status_code == 200
    assert "PRIVATE-NOTE-MARKER" in staff_notes.text


def test_all_ticket_mutations_require_csrf(actor_factory: ActorFactory) -> None:
    requester = actor_factory("requester@example.com", "user")
    ticket = create_ticket(requester)
    response = requester.client.post(
        f"/api/v1/tickets/{ticket['id']}/comments",
        json={"body": "No CSRF token"},
    )
    assert response.status_code == 422


def test_sensitive_ticket_content_and_search_terms_never_reach_logs(
    actor_factory: ActorFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    requester = actor_factory("requester@example.com", "user")
    agent = actor_factory("agent@example.com", "agent")
    configure_logging(get_settings())
    ticket = create_ticket(
        requester,
        title="Sensitive content log test",
        description="DESCRIPTION-SECRET-MARKER",
    )
    token = csrf(requester.client)
    requester.client.post(
        f"/api/v1/tickets/{ticket['id']}/comments",
        headers={"X-CSRF-Token": token},
        json={"body": "COMMENT-SECRET-MARKER"},
    )
    token = csrf(agent.client)
    agent.client.post(
        f"/api/v1/tickets/{ticket['id']}/internal-notes",
        headers={"X-CSRF-Token": token},
        json={"body": "NOTE-SECRET-MARKER"},
    )
    requester.client.get("/api/v1/tickets", params={"query": "QUERY-SECRET-MARKER"})
    output = capsys.readouterr().out

    records = [json.loads(line) for line in output.splitlines()]
    assert records
    assert any(record.get("event_name") == "search.executed" for record in records)
    for marker in (
        "DESCRIPTION-SECRET-MARKER",
        "COMMENT-SECRET-MARKER",
        "NOTE-SECRET-MARKER",
        "QUERY-SECRET-MARKER",
        "requester@example.com",
    ):
        assert marker not in output
    structlog.contextvars.clear_contextvars()
