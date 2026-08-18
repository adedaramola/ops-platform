from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from opsdesk.auth.dependencies import (
    AppSettings,
    AuthServiceDependency,
    CurrentPrincipal,
    OptionalPrincipal,
)
from opsdesk.auth.http import (
    clear_session_cookie,
    set_csrf_cookie,
    set_session_cookie,
    validate_csrf,
)
from opsdesk.auth.schemas import RegisterRequest
from opsdesk.auth.security import get_csrf_manager
from opsdesk.core.errors import AppError
from opsdesk.observability.middleware import get_request_id
from opsdesk.web.templates import templates

router = APIRouter(tags=["browser"])


def _render_auth_form(
    *,
    request: Request,
    settings: AppSettings,
    template_name: str,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    token = get_csrf_manager().issue()
    response = templates.TemplateResponse(
        request=request,
        name=template_name,
        context={"error": error, "csrf_token": token},
        status_code=status_code,
    )
    set_csrf_cookie(response, settings, token)
    return response


@router.get("/", include_in_schema=False)
def home(principal: OptionalPrincipal) -> RedirectResponse:
    return RedirectResponse("/account" if principal is not None else "/login")


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, settings: AppSettings) -> Response:
    return _render_auth_form(request=request, settings=settings, template_name="auth/register.html")


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    settings: AppSettings,
    auth_service: AuthServiceDependency,
    email: Annotated[str, Form(max_length=320)],
    password: Annotated[str, Form(min_length=1, max_length=128)],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> Response:
    try:
        validate_csrf(request, csrf_token, settings, None)
        payload = RegisterRequest(email=email, password=password)
        auth_service.register(payload.email, payload.password, get_request_id(request))
    except (AppError, ValidationError) as error:
        message = (
            error.message if isinstance(error, AppError) else "Registration details are invalid"
        )
        return _render_auth_form(
            request=request,
            settings=settings,
            template_name="auth/register.html",
            error=message,
            status_code=getattr(error, "status_code", status.HTTP_422_UNPROCESSABLE_ENTITY),
        )
    return RedirectResponse("/login?registered=1", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, settings: AppSettings) -> Response:
    return _render_auth_form(request=request, settings=settings, template_name="auth/login.html")


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    settings: AppSettings,
    auth_service: AuthServiceDependency,
    email: Annotated[str, Form(max_length=320)],
    password: Annotated[str, Form(min_length=1, max_length=128)],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> Response:
    try:
        validate_csrf(request, csrf_token, settings, None)
        client_address = request.client.host if request.client is not None else "unknown"
        result = auth_service.login(email, password, client_address, get_request_id(request))
    except AppError as error:
        return _render_auth_form(
            request=request,
            settings=settings,
            template_name="auth/login.html",
            error=error.message,
            status_code=error.status_code,
        )
    response = RedirectResponse("/account", status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookie(response, result.raw_session_token, settings)
    return response


@router.get("/account", response_class=HTMLResponse)
def account_page(
    request: Request, settings: AppSettings, principal: CurrentPrincipal
) -> HTMLResponse:
    token = get_csrf_manager().issue(principal.session.csrf_secret)
    response = templates.TemplateResponse(
        request=request,
        name="auth/account.html",
        context={"user": principal.user, "csrf_token": token},
    )
    set_csrf_cookie(response, settings, token)
    return response


@router.post("/logout")
def logout_submit(
    request: Request,
    settings: AppSettings,
    auth_service: AuthServiceDependency,
    principal: CurrentPrincipal,
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    auth_service.logout(principal, get_request_id(request))
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    clear_session_cookie(response, settings)
    return response
