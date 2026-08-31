from __future__ import annotations

import re
import time
import uuid

import structlog.contextvars
from fastapi import Request, Response
from opentelemetry import propagate
from opentelemetry.trace import Span, Status, StatusCode
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from opsdesk.core.config import Settings
from opsdesk.observability.logging import get_logger
from opsdesk.observability.metrics import OpsMetrics
from opsdesk.observability.tracing import Telemetry

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
TRACEPARENT_PATTERN = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def get_traceparent(request: Request) -> str | None:
    return getattr(request.state, "traceparent", None)


def get_route_template(request: Request) -> str:
    route = request.scope.get("route")
    return str(getattr(route, "path", "unmatched"))


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: object,
        settings: Settings,
        metrics: OpsMetrics,
        telemetry: Telemetry,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.settings = settings
        self.metrics = metrics
        self.telemetry = telemetry

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        parent_context = propagate.extract(dict(request.headers))
        with self.telemetry.server_span(request.method, parent_context) as span:
            return await self._dispatch_traced(request, call_next, span)

    async def _dispatch_traced(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        span: Span,
    ) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else str(uuid.uuid4())
        request.state.request_id = request_id
        incoming_traceparent = request.headers.get("traceparent", "")
        request.state.traceparent = (
            incoming_traceparent
            if TRACEPARENT_PATTERN.fullmatch(incoming_traceparent)
            else self.telemetry.current_traceparent()
        )
        traffic_source = "demo" if request.headers.get("X-Traffic-Source") == "demo" else "user"
        request.state.traffic_source = traffic_source
        started = time.perf_counter()
        status_code = 500
        self.metrics.http_requests_active.inc()
        structlog.contextvars.clear_contextvars()
        trace_id = self.telemetry.current_trace_id()
        structlog.contextvars.bind_contextvars(
            service=self.settings.service_name,
            environment=self.settings.environment,
            application_version=self.settings.version,
            request_id=request_id,
            trace_id=trace_id,
            traffic_source=traffic_source,
        )
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            if trace_id is not None:
                response.headers["X-Trace-ID"] = trace_id
            return response
        finally:
            route_template = get_route_template(request)
            duration_seconds = time.perf_counter() - started
            self.metrics.observe_request(
                method=request.method,
                route=route_template,
                status_code=status_code,
                duration_seconds=duration_seconds,
            )
            self.metrics.http_requests_active.dec()
            span.update_name(f"{request.method} {route_template}")
            span.set_attribute("http.route", route_template)
            span.set_attribute("http.response.status_code", status_code)
            span.set_attribute("opsdesk.traffic_source", traffic_source)
            if status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
            get_logger().info(
                "request.completed",
                event_name="request.completed",
                http_method=request.method,
                route_template=route_template,
                http_status=status_code,
                duration_ms=round(duration_seconds * 1000, 3),
            )
            structlog.contextvars.clear_contextvars()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; img-src 'self' data:; "
            "script-src 'self' https://unpkg.com; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
