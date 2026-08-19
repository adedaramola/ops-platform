from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Request

from opsdesk.auth.dependencies import AppSettings, CurrentPrincipal
from opsdesk.auth.http import validate_csrf
from opsdesk.observability.middleware import get_request_id
from opsdesk.users.dependencies import UserAdminServiceDependency
from opsdesk.users.schemas import UserActivationUpdate, UserAdminResponse, UserRoleUpdate

router = APIRouter(prefix="/api/v1/users", tags=["user administration"])
CsrfHeader = Annotated[str, Header(alias="X-CSRF-Token", min_length=1, max_length=256)]


@router.get("", response_model=list[UserAdminResponse])
def list_users(
    principal: CurrentPrincipal, service: UserAdminServiceDependency
) -> list[UserAdminResponse]:
    return [UserAdminResponse.model_validate(user) for user in service.list(principal)]


@router.patch("/{user_id}/role", response_model=UserAdminResponse)
def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: UserAdminServiceDependency,
) -> UserAdminResponse:
    validate_csrf(request, csrf_token, settings, principal)
    user = service.set_role(principal, user_id, payload.role, get_request_id(request))
    return UserAdminResponse.model_validate(user)


@router.patch("/{user_id}/activation", response_model=UserAdminResponse)
def update_user_activation(
    user_id: uuid.UUID,
    payload: UserActivationUpdate,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: UserAdminServiceDependency,
) -> UserAdminResponse:
    validate_csrf(request, csrf_token, settings, principal)
    user = service.set_active(principal, user_id, payload.is_active, get_request_id(request))
    return UserAdminResponse.model_validate(user)
