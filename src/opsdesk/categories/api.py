from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Request, status

from opsdesk.auth.dependencies import AppSettings, CurrentPrincipal
from opsdesk.auth.http import validate_csrf
from opsdesk.categories.dependencies import CategoryServiceDependency
from opsdesk.categories.schemas import CategoryCreate, CategoryResponse, CategoryUpdate
from opsdesk.observability.middleware import get_request_id

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])
CsrfHeader = Annotated[str, Header(alias="X-CSRF-Token", min_length=1, max_length=256)]


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    principal: CurrentPrincipal, service: CategoryServiceDependency
) -> list[CategoryResponse]:
    return [CategoryResponse.model_validate(item) for item in service.list(principal)]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: CategoryServiceDependency,
) -> CategoryResponse:
    validate_csrf(request, csrf_token, settings, principal)
    category = service.create(principal, payload, get_request_id(request))
    return CategoryResponse.model_validate(category)


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: CategoryServiceDependency,
) -> CategoryResponse:
    validate_csrf(request, csrf_token, settings, principal)
    category = service.update(principal, category_id, payload, get_request_id(request))
    return CategoryResponse.model_validate(category)
