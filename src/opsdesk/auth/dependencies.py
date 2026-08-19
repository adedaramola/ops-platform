from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from opsdesk.auth.service import AuthPrincipal, AuthService
from opsdesk.core.config import Settings, get_settings
from opsdesk.core.errors import AuthenticationError
from opsdesk.db.session import get_db_session
from opsdesk.observability.dependencies import MetricsDependency, TelemetryDependency

DatabaseSession = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
session_cookie_scheme = APIKeyCookie(name="opsdesk_session", auto_error=False)
DeclaredSessionCookie = Annotated[str | None, Security(session_cookie_scheme)]


def get_auth_service(
    db: DatabaseSession,
    settings: AppSettings,
    metrics: MetricsDependency,
    telemetry: TelemetryDependency,
) -> AuthService:
    return AuthService(db, settings, metrics, telemetry)


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


def get_optional_principal(
    request: Request,
    auth_service: AuthServiceDependency,
    settings: AppSettings,
    declared_session_cookie: DeclaredSessionCookie,
) -> AuthPrincipal | None:
    raw_token = request.cookies.get(settings.session_cookie_name) or declared_session_cookie
    if not raw_token:
        return None
    try:
        principal = auth_service.authenticate_session(raw_token)
    except AuthenticationError:
        return None
    request.state.user_id = str(principal.user.id)
    return principal


OptionalPrincipal = Annotated[AuthPrincipal | None, Depends(get_optional_principal)]


def get_current_principal(principal: OptionalPrincipal) -> AuthPrincipal:
    if principal is None:
        raise AuthenticationError()
    return principal


CurrentPrincipal = Annotated[AuthPrincipal, Depends(get_current_principal)]
