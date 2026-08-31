from __future__ import annotations

import json
import uuid
from typing import Any

from pytest import MonkeyPatch

from opsdesk.ai import dispatch


class _SqsClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def send_message(self, **message: Any) -> None:
        self.messages.append(message)


def test_sqs_dispatch_preserves_bounded_trace_context(monkeypatch: MonkeyPatch) -> None:
    client = _SqsClient()
    monkeypatch.setattr(dispatch.boto3, "client", lambda _service: client)
    workflow_id = uuid.uuid4()
    traceparent = "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"

    dispatcher = dispatch.SqsWorkflowDispatcher("https://sqs.example.test/agent")
    dispatcher.publish(workflow_id, traceparent)

    assert client.messages == [
        {
            "QueueUrl": "https://sqs.example.test/agent",
            "MessageBody": json.dumps(
                {"workflow_id": str(workflow_id), "traceparent": traceparent},
                separators=(",", ":"),
            ),
        }
    ]


def test_sqs_dispatch_omits_absent_trace_context(monkeypatch: MonkeyPatch) -> None:
    client = _SqsClient()
    monkeypatch.setattr(dispatch.boto3, "client", lambda _service: client)
    workflow_id = uuid.uuid4()

    dispatcher = dispatch.SqsWorkflowDispatcher("https://sqs.example.test/agent")
    dispatcher.publish(workflow_id)

    body = json.loads(client.messages[0]["MessageBody"])
    assert body == {"workflow_id": str(workflow_id)}
