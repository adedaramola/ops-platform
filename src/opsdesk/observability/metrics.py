from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST


class OpsMetrics:
    """Per-application Prometheus instruments with deliberately bounded labels."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.http_requests = Counter(
            "opsdesk_http_requests_total",
            "Completed HTTP requests.",
            ("method", "route", "status_class"),
            registry=self.registry,
        )
        self.http_request_duration = Histogram(
            "opsdesk_http_request_duration_seconds",
            "HTTP request duration in seconds.",
            ("method", "route"),
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
            registry=self.registry,
        )
        self.http_requests_active = Gauge(
            "opsdesk_http_requests_active",
            "HTTP requests currently being processed.",
            registry=self.registry,
        )
        self.login_attempts = Counter(
            "opsdesk_login_attempts_total",
            "Authentication login attempts by bounded outcome.",
            ("outcome",),
            registry=self.registry,
        )
        self.tickets_created = Counter(
            "opsdesk_tickets_created_total",
            "Tickets created by priority.",
            ("priority",),
            registry=self.registry,
        )
        self.ticket_status_transitions = Counter(
            "opsdesk_ticket_status_transitions_total",
            "Ticket status transitions.",
            ("from_status", "to_status"),
            registry=self.registry,
        )
        self.authorization_denials = Counter(
            "opsdesk_authorization_denials_total",
            "Authorization denials by route template and method.",
            ("method", "route"),
            registry=self.registry,
        )
        self.database_errors = Counter(
            "opsdesk_database_errors_total",
            "Database errors by bounded operation class.",
            ("operation",),
            registry=self.registry,
        )
        self.application_errors = Counter(
            "opsdesk_application_errors_total",
            "Application errors by bounded category.",
            ("category",),
            registry=self.registry,
        )

        for outcome in ("succeeded", "invalid_credentials", "rate_limited"):
            self.login_attempts.labels(outcome=outcome)
        for priority in ("low", "medium", "high", "critical"):
            self.tickets_created.labels(priority=priority)

    def render(self) -> tuple[bytes, str]:
        return generate_latest(self.registry), CONTENT_TYPE_LATEST

    def observe_request(
        self, *, method: str, route: str, status_code: int, duration_seconds: float
    ) -> None:
        status_class = f"{status_code // 100}xx"
        self.http_requests.labels(
            method=method,
            route=route,
            status_class=status_class,
        ).inc()
        self.http_request_duration.labels(method=method, route=route).observe(duration_seconds)
