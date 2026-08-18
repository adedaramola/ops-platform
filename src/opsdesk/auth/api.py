from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status

from opsdesk.auth.dependencies import (
    AppSettings,
    AuthServiceDependency,
    CurrentPrincipal,
    OptionalPrincipal,
)
from opsdesk.auth.http import (
    clear_session_cookie,
    issue_csrf_cookie,
    set_session_cookie,
    validate_csrf,
)
from opsdesk.auth.schemas import (
    AuthStatusResponse,
    CsrfResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from opsdesk.observability.middleware import get_request_id

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
CsrfHeader = Annotated[str, Header(alias="X-CSRF-Token", min_length=1, max_length=256)]


def _user_response(principal: CurrentPrincipal) -> UserResponse:
    return UserResponse(
        id=principal.user.id,
        role=principal.user.role_key,
        is_active=principal.user.is_active,
    )


@router.get("/csrf", response_model=CsrfResponse)
def csrf_token(
    response: Response, settings: AppSettings, principal: OptionalPrincipal
) -> CsrfResponse:
    token = issue_csrf_cookie(response, settings, principal)
    return CsrfResponse(csrf_token=token)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    csrf_token: CsrfHeader,
    auth_service: AuthServiceDependency,
    settings: AppSettings,
    principal: OptionalPrincipal,
) -> UserResponse:
    validate_csrf(request, csrf_token, settings, principal)
    user = auth_service.register(payload.email, payload.password, get_request_id(request))
    return UserResponse(id=user.id, role=user.role_key, is_active=user.is_active)


@router.post("/login", response_model=AuthStatusResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    csrf_token: CsrfHeader,
    auth_service: AuthServiceDependency,
    settings: AppSettings,
    principal: OptionalPrincipal,
) -> AuthStatusResponse:
    validate_csrf(request, csrf_token, settings, principal)
    client_address = request.client.host if request.client is not None else "unknown"
    result = auth_service.login(
        payload.email,
        payload.password,
        client_address,
        get_request_id(request),
    )
    set_session_cookie(response, result.raw_session_token, settings)
    return AuthStatusResponse(authenticated=True, user=_user_response(result.principal))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    csrf_token: CsrfHeader,
    auth_service: AuthServiceDependency,
    settings: AppSettings,
    principal: CurrentPrincipal,
) -> None:
    validate_csrf(request, csrf_token, settings, principal)
    auth_service.logout(principal, get_request_id(request))
    clear_session_cookie(response, settings)


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(principal: OptionalPrincipal) -> AuthStatusResponse:
    if principal is None:
        return AuthStatusResponse(authenticated=False)
    return AuthStatusResponse(authenticated=True, user=_user_response(principal))
