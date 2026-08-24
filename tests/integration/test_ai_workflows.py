from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from opsdesk.ai.models import AiWorkflow
from opsdesk.db.session import get_session_factory
from tests.helpers import csrf
from tests.phase3_helpers import ActorFactory, command, create_ticket

AGENT_HEADERS = {"X-OpsDesk-Agent-Token": "test-agent-service-token"}


def _result(content: str = "Please restart the VPN client and try again.") -> dict[str, object]:
    return {
        "suggestion_type": "draft_public_response",
        "content": content,
        "decision_summary": "Used the deterministic draft tool.",
        "selected_tools": ["draft_public_response"],
        "provider_class": "deterministic-fake",
        "model_class": "phase7-contract-fixture",
        "generation_ms": 3,
        "estimated_cost_usd": None,
        "rag_used": False,
        "citations": [],
    }


def test_ai_draft_requires_staff_review_and_is_idempotently_applied(
    actor_factory: ActorFactory,
) -> None:
    requester = actor_factory("ai-requester@example.com", "user")
    agent = actor_factory("ai-agent@example.com", "agent")
    ticket = create_ticket(requester, title="VPN client cannot connect")
    claim = command(
        agent,
        f"/api/v1/tickets/{ticket['id']}/assignment",
        {"assignee_id": str(agent.user.id), "expected_version": ticket["version"]},
    )
    assert claim.status_code == 200
    note = command(
        agent,
        f"/api/v1/tickets/{ticket['id']}/internal-notes",
        {"body": "PRIVATE-AI-MARKER must not leave OpsDesk"},
    )
    assert note.status_code == 201

    token = csrf(agent.client)
    request = agent.client.post(
        f"/api/v1/tickets/{ticket['id']}/ai-suggestions",
        headers={"X-CSRF-Token": token},
        json={"idempotency_key": "vpn-draft-request-001"},
    )
    duplicate = agent.client.post(
        f"/api/v1/tickets/{ticket['id']}/ai-suggestions",
        headers={"X-CSRF-Token": token},
        json={"idempotency_key": "vpn-draft-request-001"},
    )
    assert request.status_code == duplicate.status_code == 202
    assert request.json()["id"] == duplicate.json()["id"]
    workflow_id = request.json()["id"]

    denied = requester.client.get(f"/api/v1/ai-workflows/{workflow_id}")
    bad_service_token = agent.client.get(
        f"/internal/v1/ai-workflows/{workflow_id}/context",
        headers={"X-OpsDesk-Agent-Token": "wrong"},
    )
    context = agent.client.get(
        f"/internal/v1/ai-workflows/{workflow_id}/context", headers=AGENT_HEADERS
    )
    assert denied.status_code == 403
    assert bad_service_token.status_code == 401
    assert context.status_code == 200
    assert "PRIVATE-AI-MARKER" not in context.text
    assert "ai-requester@example.com" not in context.text

    result = agent.client.post(
        f"/internal/v1/ai-workflows/{workflow_id}/result",
        headers=AGENT_HEADERS,
        json=_result(),
    )
    replayed_result = agent.client.post(
        f"/internal/v1/ai-workflows/{workflow_id}/result",
        headers=AGENT_HEADERS,
        json=_result("A replay must not replace the original."),
    )
    assert result.status_code == replayed_result.status_code == 200
    suggestion = result.json()["suggestion"]
    assert suggestion["approval_state"] == "pending"
    assert suggestion["gateway_request_id"] is None
    assert suggestion["input_tokens"] == 0
    assert suggestion["output_tokens"] == 0
    assert suggestion["cache_policy"] == "not_applicable"
    assert suggestion["cache_source"] == "not_applicable"
    assert suggestion["cache_hit"] is False
    assert replayed_result.json()["suggestion"]["content"] == suggestion["content"]

    edited = "Please restart the VPN client. Reply here if the issue continues."
    approval = agent.client.post(
        f"/api/v1/ai-suggestions/{suggestion['id']}/approve",
        headers={"X-CSRF-Token": csrf(agent.client)},
        json={"content": edited},
    )
    assert approval.status_code == 200
    assert approval.json()["approval_state"] == "approved"
    assert approval.json()["content"] == edited

    application = agent.client.post(
        f"/api/v1/ai-suggestions/{suggestion['id']}/apply",
        headers={"X-CSRF-Token": csrf(agent.client)},
    )
    replayed_application = agent.client.post(
        f"/api/v1/ai-suggestions/{suggestion['id']}/apply",
        headers={"X-CSRF-Token": csrf(agent.client)},
    )
    assert application.status_code == replayed_application.status_code == 200
    assert application.json()["comment_id"] == replayed_application.json()["comment_id"]
    detail = requester.client.get(f"/api/v1/tickets/{ticket['id']}")
    assert edited in [comment["body"] for comment in detail.json()["comments"]]


def test_stale_ai_suggestion_cannot_be_approved(actor_factory: ActorFactory) -> None:
    requester = actor_factory("stale-requester@example.com", "user")
    admin = actor_factory("stale-admin@example.com", "admin")
    ticket = create_ticket(requester)
    token = csrf(admin.client)
    request = admin.client.post(
        f"/api/v1/tickets/{ticket['id']}/ai-suggestions",
        headers={"X-CSRF-Token": token},
        json={},
    )
    workflow_id = request.json()["id"]
    result = admin.client.post(
        f"/internal/v1/ai-workflows/{workflow_id}/result",
        headers=AGENT_HEADERS,
        json=_result(),
    )
    suggestion_id = result.json()["suggestion"]["id"]
    changed = command(
        admin,
        f"/api/v1/tickets/{ticket['id']}/priority",
        {"priority": "high", "expected_version": ticket["version"]},
    )
    assert changed.status_code == 200
    approval = admin.client.post(
        f"/api/v1/ai-suggestions/{suggestion_id}/approve",
        headers={"X-CSRF-Token": csrf(admin.client)},
        json={},
    )
    assert approval.status_code == 409
    assert approval.json()["error"]["code"] == "CONFLICT"


def test_completed_workflow_context_remains_successful_after_deadline(
    actor_factory: ActorFactory,
) -> None:
    admin = actor_factory("completed-workflow-admin@example.com", "admin")
    ticket = create_ticket(admin, title="Completed workflow deadline regression")
    request = admin.client.post(
        f"/api/v1/tickets/{ticket['id']}/ai-suggestions",
        headers={"X-CSRF-Token": csrf(admin.client)},
        json={},
    )
    workflow_id = request.json()["id"]
    result = admin.client.post(
        f"/internal/v1/ai-workflows/{workflow_id}/result",
        headers=AGENT_HEADERS,
        json=_result(),
    )
    assert result.status_code == 200
    assert result.json()["status"] == "succeeded"

    with get_session_factory()() as session:
        workflow = session.scalar(select(AiWorkflow).where(AiWorkflow.id == workflow_id))
        assert workflow is not None
        workflow.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    context = admin.client.get(
        f"/internal/v1/ai-workflows/{workflow_id}/context",
        headers=AGENT_HEADERS,
    )
    workflow = admin.client.get(f"/api/v1/ai-workflows/{workflow_id}")
    assert context.status_code == 200
    assert workflow.status_code == 200
    assert workflow.json()["status"] == "succeeded"
    assert workflow.json()["failure_code"] is None
