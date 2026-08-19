from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    status_code: int


class AuthenticationError(AppError):
    def __init__(self) -> None:
        super().__init__("AUTHENTICATION_FAILED", "Unable to authenticate", 401)


class AuthorizationError(AppError):
    def __init__(self) -> None:
        super().__init__("AUTHORIZATION_DENIED", "You are not allowed to perform this action", 403)


class ConflictError(AppError):
    def __init__(
        self, message: str = "The requested operation conflicts with existing data"
    ) -> None:
        super().__init__("CONFLICT", message, 409)


class CsrfError(AppError):
    def __init__(self) -> None:
        super().__init__("CSRF_VALIDATION_FAILED", "The form security token is invalid", 403)


class RateLimitError(AppError):
    def __init__(self) -> None:
        super().__init__("RATE_LIMIT_EXCEEDED", "Too many attempts; try again later", 429)


class NotFoundError(AppError):
    def __init__(self, message: str = "The requested resource was not found") -> None:
        super().__init__("NOT_FOUND", message, 404)


class WorkflowError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("WORKFLOW_RULE_VIOLATION", message, 422)
