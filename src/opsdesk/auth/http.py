from __future__ import annotations

import hmac

from fastapi import Request, Response

from opsdesk.auth.security import get_csrf_manager
from opsdesk.auth.service import AuthPrincipal
from opsdesk.core.config import Settings
from opsdesk.core.errors import CsrfError


def set_session_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_absolute_minutes * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def issue_csrf_cookie(
    response: Response, settings: Settings, principal: AuthPrincipal | None
) -> str:
    secret = principal.session.csrf_secret if principal is not None else None
    token = get_csrf_manager().issue(secret)
    set_csrf_cookie(response, settings, token)
    return token


def set_csrf_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        max_age=settings.csrf_max_age_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def validate_csrf(
    request: Request,
    supplied_token: str,
    settings: Settings,
    principal: AuthPrincipal | None,
) -> None:
    cookie_token = request.cookies.get(settings.csrf_cookie_name, "")
    if not cookie_token or not hmac.compare_digest(cookie_token, supplied_token):
        raise CsrfError()
    secret = principal.session.csrf_secret if principal is not None else None
    if not get_csrf_manager().validate(supplied_token, secret):
        raise CsrfError()
