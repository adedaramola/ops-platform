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
        self.ai_workflows = Counter(
            "opsdesk_ai_workflows_total",
            "AI workflows by bounded outcome.",
            ("outcome",),
            registry=self.registry,
        )
        self.ai_workflow_duration = Histogram(
            "opsdesk_ai_workflow_duration_seconds",
            "AI workflow duration from request through Agent result.",
            ("outcome",),
            buckets=(0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
            registry=self.registry,
        )
        self.ai_generation = Counter(
            "opsdesk_ai_generation_total",
            "Completed generation by bounded provider, model tier, and grounding state.",
            ("provider_class", "model_class", "rag_used"),
            registry=self.registry,
        )
        self.ai_tokens = Counter(
            "opsdesk_ai_tokens_total",
            "Gateway tokens recorded by direction.",
            ("direction",),
            registry=self.registry,
        )
        self.ai_estimated_cost = Counter(
            "opsdesk_ai_estimated_cost_usd_total",
            "Estimated gateway cost recorded by bounded provider class.",
            ("provider_class",),
            registry=self.registry,
        )
        self.ai_reviews = Counter(
            "opsdesk_ai_reviews_total",
            "Human review events by bounded action.",
            ("action",),
            registry=self.registry,
        )
        self.ai_time_to_review = Histogram(
            "opsdesk_ai_time_to_review_seconds",
            "Elapsed time from generation to human approval or rejection.",
            ("action",),
            buckets=(5, 15, 30, 60, 300, 900, 3600, 21600, 86400),
            registry=self.registry,
        )

        for outcome in ("succeeded", "invalid_credentials", "rate_limited"):
            self.login_attempts.labels(outcome=outcome)
        for priority in ("low", "medium", "high", "critical"):
            self.tickets_created.labels(priority=priority)
        for outcome in ("requested", "succeeded", "failed", "cancelled"):
            self.ai_workflows.labels(outcome=outcome)
        for action in ("edited", "approved", "rejected", "applied"):
            self.ai_reviews.labels(action=action)

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
