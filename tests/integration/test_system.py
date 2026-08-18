from __future__ import annotations

import json
import logging

import pytest
import structlog
from fastapi.testclient import TestClient

from opsdesk.api import system
from opsdesk.core.config import get_settings
from opsdesk.observability.logging import configure_logging


def test_health_and_status_endpoints(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "live"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    assert client.get("/health").json() == {"status": "healthy"}
    assert client.get("/ready").json() == {"status": "ready"}
    body = client.get("/api/v1/status").json()
    assert body["service"] == "opsdesk"
    assert body["status"] == "operational"


def test_request_id_is_generated_or_propagated(client: TestClient) -> None:
    generated = client.get("/health/live")
    propagated = client.get("/health/live", headers={"X-Request-ID": "known-request-1"})
    rejected = client.get("/health/live", headers={"X-Request-ID": "bad request id"})

    assert generated.headers["X-Request-ID"]
    assert propagated.headers["X-Request-ID"] == "known-request-1"
    assert rejected.headers["X-Request-ID"] != "bad request id"


def test_liveness_survives_database_outage(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(system, "_database_ready", lambda: False)

    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 503
    assert client.get("/health").status_code == 503


def test_logs_are_json_and_redact_sensitive_fields(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(get_settings())
    client.get("/health/live", headers={"X-Request-ID": "log-test"})
    structlog.get_logger().info(
        "redaction.test",
        event_name="redaction.test",
        email="person@example.com",
        password="SensitivePassword!99",
    )
    logging.getLogger("uvicorn.error").info("framework.started")
    output = capsys.readouterr().out
    lines = output.splitlines()
    assert lines
    records = [json.loads(line) for line in lines]
    request_record = next(record for record in records if record.get("request_id") == "log-test")
    assert request_record["event_name"] == "request.completed"
    assert request_record["route_template"] == "/health/live"
    redaction_record = next(
        record for record in records if record.get("event_name") == "redaction.test"
    )
    framework_record = next(
        record for record in records if record.get("event") == "framework.started"
    )
    assert redaction_record["email"] == "[REDACTED]"
    assert redaction_record["password"] == "[REDACTED]"
    assert framework_record["service"] == "opsdesk"
    assert "person@example.com" not in output
    assert "SensitivePassword!99" not in output
