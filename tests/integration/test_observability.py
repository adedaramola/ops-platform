from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy.exc import OperationalError

from opsdesk.core.config import Settings, get_settings
from opsdesk.main import create_app
from tests.helpers import csrf, login, register
from tests.phase3_helpers import GENERAL_CATEGORY_ID


def _samples(body: str, metric_name: str) -> list[object]:
    for family in text_string_to_metric_families(body):
        if family.name == metric_name:
            return list(family.samples)
    raise AssertionError(f"Metric family {metric_name} was not exposed")


def test_metrics_exposition_uses_route_templates_and_bounded_labels(
    client: TestClient,
) -> None:
    assert register(client).status_code == 201
    assert login(client).status_code == 200
    token = csrf(client)
    ticket = client.post(
        "/api/v1/tickets",
        headers={"X-CSRF-Token": token},
        json={
            "title": "Metrics privacy marker",
            "description": "METRICS-SENSITIVE-DESCRIPTION",
            "category_id": str(GENERAL_CATEGORY_ID),
            "priority": "critical",
        },
    ).json()
    client.get(f"/api/v1/tickets/{ticket['id']}")
    denied = client.get(f"/api/v1/tickets/{ticket['id']}/internal-notes")
    assert denied.status_code == 403

    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    request_samples = _samples(body, "opsdesk_http_requests")
    assert any(
        sample.labels
        == {
            "method": "GET",
            "route": "/api/v1/tickets/{ticket_id}",
            "status_class": "2xx",
        }
        for sample in request_samples
    )
    assert 'priority="critical"' in body
    assert 'outcome="succeeded"' in body
    assert "opsdesk_authorization_denials_total" in body
    assert "opsdesk_http_requests_active" in body
    assert str(ticket["id"]) not in body
    assert "person@example.com" not in body
    assert "METRICS-SENSITIVE-DESCRIPTION" not in body


def test_database_and_application_errors_are_counted_without_details() -> None:
    app = create_app(get_settings())

    @app.get("/test/database-error")
    def database_error() -> None:
        raise OperationalError("SELECT secret", {}, RuntimeError("DB-SECRET-MARKER"))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test/database-error")
        metrics = client.get("/metrics").text

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert 'operation="request"' in metrics
    assert "DB-SECRET-MARKER" not in metrics
    assert "SELECT secret" not in metrics


def test_trace_context_propagates_to_response_logs_and_database_spans(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exporter = InMemorySpanExporter()
    settings = Settings(
        environment="test",
        otel_enabled=True,
        otel_sample_ratio=1.0,
        session_cookie_secure=False,
        csrf_secret_key="trace-test-secret",
    )
    trace_id = "1234567890abcdef1234567890abcdef"
    with TestClient(create_app(settings, span_exporter=exporter)) as client:
        response = client.get(
            "/health/ready",
            headers={
                "traceparent": f"00-{trace_id}-1234567890abcdef-01",
                "X-Request-ID": "trace-request-test",
            },
        )
        assert register(client, email="trace-person@example.com").status_code == 201
        assert login(client, email="trace-person@example.com").status_code == 200
        token = csrf(client)
        created = client.post(
            "/api/v1/tickets",
            headers={"X-CSRF-Token": token},
            json={
                "title": "Trace privacy ticket",
                "description": "TRACE-DESCRIPTION-SECRET",
                "category_id": str(GENERAL_CATEGORY_ID),
                "priority": "medium",
            },
        )
        assert created.status_code == 201
        client.get("/api/v1/tickets", params={"query": "TRACE-QUERY-SECRET"})
        client.app.state.telemetry.force_flush()
        spans = exporter.get_finished_spans()
        output = capsys.readouterr().out

    assert response.status_code == 200
    assert response.headers["X-Trace-ID"] == trace_id
    records = [json.loads(line) for line in output.splitlines()]
    request_log = next(
        record for record in records if record.get("request_id") == "trace-request-test"
    )
    assert request_log["trace_id"] == trace_id
    assert any(span.kind.name == "SERVER" for span in spans)
    assert any("SELECT" in span.name.upper() for span in spans)
    assert any(span.name == "auth.login" for span in spans)
    assert any(span.name == "ticket.create" for span in spans)
    serialized = json.dumps(
        [{"name": span.name, "attributes": dict(span.attributes or {})} for span in spans],
        default=str,
    )
    for sensitive_value in (
        "trace-test-secret",
        "trace-person@example.com",
        "TRACE-DESCRIPTION-SECRET",
        "TRACE-QUERY-SECRET",
    ):
        assert sensitive_value not in serialized


def test_unavailable_trace_collector_does_not_affect_requests_or_readiness() -> None:
    settings = Settings(
        environment="test",
        otel_enabled=True,
        otel_exporter_otlp_endpoint="http://127.0.0.1:1/v1/traces",
        otel_export_timeout_seconds=0.05,
        session_cookie_secure=False,
        csrf_secret_key="collector-outage-test-secret",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200


def test_traffic_source_is_bounded_and_never_grants_access(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with TestClient(create_app(get_settings())) as client:
        spoofed = client.get(
            "/api/v1/tickets",
            headers={"X-Traffic-Source": "demo-unbounded-value"},
        )
        demo = client.get(
            f"/api/v1/tickets/{uuid.uuid4()}",
            headers={"X-Traffic-Source": "demo"},
        )
        output = capsys.readouterr().out

    assert spoofed.status_code == 401
    assert demo.status_code == 401
    records = [json.loads(line) for line in output.splitlines()]
    completed = [record for record in records if record.get("event_name") == "request.completed"]
    assert {record["traffic_source"] for record in completed} == {"user", "demo"}
    assert "demo-unbounded-value" not in output


def test_development_controlled_failures_are_bounded_and_observable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        environment="development",
        enable_controlled_failures=True,
        controlled_failure_max_delay_ms=10,
        session_cookie_secure=False,
        csrf_secret_key="controlled-failure-test-secret",
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        assert register(client, email="failure-test@example.com").status_code == 201
        assert login(client, email="failure-test@example.com").status_code == 200
        assert (
            client.get("/api/v1/development/failures/slow", params={"delay_ms": 1}).status_code
            == 200
        )
        assert (
            client.get("/api/v1/development/failures/slow", params={"delay_ms": 11}).status_code
            == 422
        )
        failure = client.get("/api/v1/development/failures/error")
        metrics = client.get("/metrics").text
        output = capsys.readouterr().out

    assert failure.status_code == 500
    assert failure.json()["error"]["code"] == "INTERNAL_ERROR"
    assert 'category="unexpected"' in metrics
    assert 'status_class="5xx"' in metrics
    assert "Controlled development failure" not in output
