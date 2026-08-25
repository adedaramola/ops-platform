from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from opsdesk.ai.models import (
    AiOutboxEvent,
    AiReviewEvent,
    AiSuggestion,
    AiWorkflow,
    OutboxStatus,
)
from opsdesk.db.base import utc_now


class AiRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_workflow(self, workflow: AiWorkflow) -> None:
        self.session.add(workflow)

    def get_workflow(self, workflow_id: uuid.UUID) -> AiWorkflow | None:
        return self.session.get(AiWorkflow, workflow_id)

    def find_idempotent_workflow(
        self, requested_by_id: uuid.UUID, idempotency_key: str
    ) -> AiWorkflow | None:
        return self.session.scalar(
            select(AiWorkflow).where(
                AiWorkflow.requested_by_id == requested_by_id,
                AiWorkflow.idempotency_key == idempotency_key,
            )
        )

    def list_ticket_workflows(self, ticket_id: uuid.UUID, limit: int = 20) -> Sequence[AiWorkflow]:
        return tuple(
            self.session.scalars(
                select(AiWorkflow)
                .where(AiWorkflow.ticket_id == ticket_id)
                .order_by(AiWorkflow.created_at.desc(), AiWorkflow.id.desc())
                .limit(limit)
            )
        )

    def add_suggestion(self, suggestion: AiSuggestion) -> None:
        self.session.add(suggestion)

    def get_suggestion(self, suggestion_id: uuid.UUID) -> AiSuggestion | None:
        return self.session.get(AiSuggestion, suggestion_id)

    def get_workflow_suggestion(self, workflow_id: uuid.UUID) -> AiSuggestion | None:
        return self.session.scalar(
            select(AiSuggestion).where(AiSuggestion.workflow_id == workflow_id)
        )

    def add_review_event(self, event: AiReviewEvent) -> None:
        self.session.add(event)

    def add_outbox_event(self, event: AiOutboxEvent) -> None:
        self.session.add(event)

    def pending_outbox(self, limit: int = 20) -> Sequence[AiOutboxEvent]:
        return tuple(
            self.session.scalars(
                select(AiOutboxEvent)
                .where(
                    AiOutboxEvent.status == OutboxStatus.PENDING,
                    AiOutboxEvent.available_at <= utc_now(),
                )
                .order_by(AiOutboxEvent.available_at, AiOutboxEvent.id)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
