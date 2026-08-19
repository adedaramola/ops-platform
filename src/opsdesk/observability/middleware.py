from __future__ import annotations

import re
import time
import uuid

import structlog.contextvars
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from opsdesk.core.config import Settings
from opsdesk.observability.logging import get_logger

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        status_code = 500
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            service=self.settings.service_name,
            environment=self.settings.environment,
            application_version=self.settings.version,
            request_id=request_id,
            trace_id=None,
        )
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            route_template = getattr(route, "path", "unmatched")
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            get_logger().info(
                "request.completed",
                event_name="request.completed",
                http_method=request.method,
                route_template=route_template,
                http_status=status_code,
                duration_ms=duration_ms,
                traffic_source=request.headers.get("X-Traffic-Source", "user"),
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
