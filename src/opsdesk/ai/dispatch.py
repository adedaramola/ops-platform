from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Protocol

import boto3
from sqlalchemy.orm import Session

from opsdesk.ai.models import OutboxStatus
from opsdesk.ai.repository import AiRepository
from opsdesk.core.config import Settings, get_settings
from opsdesk.db.base import utc_now
from opsdesk.db.session import get_session_factory
from opsdesk.observability.logging import configure_logging, get_logger


class WorkflowDispatcher(Protocol):
    def publish(self, workflow_id: uuid.UUID, traceparent: str | None = None) -> None: ...


class InMemoryDispatcher:
    def __init__(self) -> None:
        self.workflow_ids: list[uuid.UUID] = []

    def publish(self, workflow_id: uuid.UUID, traceparent: str | None = None) -> None:
        if workflow_id not in self.workflow_ids:
            self.workflow_ids.append(workflow_id)


class SqsWorkflowDispatcher:
    def __init__(self, queue_url: str) -> None:
        self.queue_url = queue_url
        self.client = boto3.client("sqs")

    def publish(self, workflow_id: uuid.UUID, traceparent: str | None = None) -> None:
        body: dict[str, str] = {"workflow_id": str(workflow_id)}
        if traceparent is not None:
            body["traceparent"] = traceparent
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(body, separators=(",", ":")),
        )


def dispatcher_for(settings: Settings) -> WorkflowDispatcher:
    if settings.ai_dispatch_mode == "memory":
        return InMemoryDispatcher()
    if settings.ai_dispatch_mode == "sqs" and settings.ai_queue_url:
        return SqsWorkflowDispatcher(settings.ai_queue_url)
    raise RuntimeError("AI workflow dispatcher is not configured")


class OutboxRelay:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        dispatcher: WorkflowDispatcher,
    ) -> None:
        self.session_factory = session_factory
        self.dispatcher = dispatcher

    def run_once(self, limit: int = 20) -> int:
        published = 0
        with self.session_factory() as session:
            events = AiRepository(session).pending_outbox(limit)
            for event in events:
                event.attempts += 1
                try:
                    workflow = AiRepository(session).get_workflow(event.workflow_id)
                    traceparent = workflow.traceparent if workflow is not None else None
                    self.dispatcher.publish(event.workflow_id, traceparent)
                except Exception as error:
                    event.last_error = type(error).__name__[:300]
                    delay = min(300, 2 ** min(event.attempts, 8))
                    event.available_at = utc_now() + timedelta(seconds=delay)
                    get_logger().warning(
                        "ai_outbox.publish_failed",
                        event_name="ai_outbox.publish_failed",
                        workflow_id=str(event.workflow_id),
                        attempt=event.attempts,
                    )
                else:
                    event.status = OutboxStatus.PUBLISHED
                    event.published_at = utc_now()
                    event.last_error = None
                    published += 1
            session.commit()
        return published


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    if not settings.ai_enabled:
        raise SystemExit("AI workflows are disabled")
    relay = OutboxRelay(get_session_factory(), dispatcher_for(settings))
    count = relay.run_once()
    get_logger().info("ai_outbox.completed", event_name="ai_outbox.completed", published=count)
