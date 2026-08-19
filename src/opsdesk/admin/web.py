from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from opsdesk.admin.dependencies import AdminServiceDependency
from opsdesk.auth.dependencies import AppSettings, CurrentPrincipal
from opsdesk.auth.http import set_csrf_cookie, validate_csrf
from opsdesk.auth.security import get_csrf_manager
from opsdesk.categories.dependencies import CategoryServiceDependency
from opsdesk.categories.schemas import CategoryCreate, CategoryUpdate
from opsdesk.observability.middleware import get_request_id
from opsdesk.users.dependencies import UserAdminServiceDependency
from opsdesk.web.templates import templates

router = APIRouter(tags=["admin browser"])


@router.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    admin_service: AdminServiceDependency,
    user_service: UserAdminServiceDependency,
    category_service: CategoryServiceDependency,
) -> Response:
    statistics = admin_service.statistics(principal)
    token = get_csrf_manager().issue(principal.session.csrf_secret)
    response = templates.TemplateResponse(
        request=request,
        name="admin/index.html",
        context={
            "principal": principal,
            "statistics": statistics,
            "users": user_service.list(principal),
            "categories": category_service.list(principal),
            "audit_events": admin_service.audit_events(principal, 50),
            "csrf_token": token,
        },
    )
    set_csrf_cookie(response, settings, token)
    return response


@router.post("/admin/users/{user_id}/role")
def admin_role_submit(
    user_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: UserAdminServiceDependency,
    role: Annotated[str, Form()],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    if role not in {"user", "agent", "admin"}:
        from opsdesk.core.errors import WorkflowError

        raise WorkflowError("Unknown user role")
    service.set_role(principal, user_id, role, get_request_id(request))
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/users/{user_id}/activation")
def admin_activation_submit(
    user_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: UserAdminServiceDependency,
    is_active: Annotated[bool, Form()],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    service.set_active(principal, user_id, is_active, get_request_id(request))
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/categories")
def admin_category_create_submit(
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: CategoryServiceDependency,
    name: Annotated[str, Form(max_length=100)],
    description: Annotated[str, Form(max_length=1000)],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    service.create(
        principal,
        CategoryCreate(name=name, description=description),
        get_request_id(request),
    )
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/categories/{category_id}/activation")
def admin_category_activation_submit(
    category_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: CategoryServiceDependency,
    is_active: Annotated[bool, Form()],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    service.update(
        principal,
        category_id,
        CategoryUpdate(is_active=is_active),
        get_request_id(request),
    )
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)
