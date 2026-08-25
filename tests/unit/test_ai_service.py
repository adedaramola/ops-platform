from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from opsdesk.ai.models import AiWorkflowStatus
from opsdesk.ai.service import AiWorkflowService


class _DatabaseStub:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class _TicketRepositoryStub:
    def __init__(self, ticket: Any) -> None:
        self.ticket = ticket

    def get(self, _ticket_id: uuid.UUID) -> Any:
        return self.ticket

    def list_comments(self, _ticket_id: uuid.UUID) -> list[Any]:
        return [SimpleNamespace(body="A public comment")]


def test_completed_workflow_context_remains_successful_after_deadline() -> None:
    workflow_id = uuid.uuid4()
    ticket_id = uuid.uuid4()
    workflow = SimpleNamespace(
        id=workflow_id,
        ticket_id=ticket_id,
        ticket_version=2,
        status=AiWorkflowStatus.SUCCEEDED,
        cancel_requested=False,
        deadline_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    ticket = SimpleNamespace(
        id=ticket_id,
        title="Completed workflow",
        description="The completed result must remain readable.",
    )
    database = _DatabaseStub()
    service = AiWorkflowService.__new__(AiWorkflowService)
    service.db = database  # type: ignore[assignment]
    service.tickets = _TicketRepositoryStub(ticket)  # type: ignore[assignment]
    service._workflow = lambda _workflow_id: workflow  # type: ignore[method-assign]

    context = service.agent_context(workflow_id)

    assert context.workflow_id == workflow_id
    assert context.public_comments == ["A public comment"]
    assert workflow.status == AiWorkflowStatus.SUCCEEDED
    assert database.commits == 0
