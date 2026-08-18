from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from opsdesk.core.errors import AppError, AuthorizationError
from opsdesk.observability.logging import get_logger
from opsdesk.observability.middleware import get_request_id


def _payload(code: str, message: str, request_id: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, error: AppError) -> JSONResponse:
        if isinstance(error, AuthorizationError):
            get_logger().warning(
                "authorization.denied", event_name="authorization.denied", outcome="denied"
            )
        return JSONResponse(
            status_code=error.status_code,
            content=_payload(error.code, error.message, get_request_id(request)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_payload(
                "VALIDATION_ERROR", "Request validation failed", get_request_id(request)
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, error: HTTPException) -> JSONResponse:
        message = error.detail if isinstance(error.detail, str) else "Request failed"
        return JSONResponse(
            status_code=error.status_code,
            content=_payload("HTTP_ERROR", message, get_request_id(request)),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
        get_logger().exception(
            "unexpected_error",
            event_name="unexpected_error",
            error_type=type(error).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_payload(
                "INTERNAL_ERROR", "An unexpected error occurred", get_request_id(request)
            ),
        )
