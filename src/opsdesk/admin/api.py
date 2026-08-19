from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from opsdesk.admin.dependencies import AdminServiceDependency
from opsdesk.admin.schemas import AdminStatisticsResponse, AuditEventResponse
from opsdesk.auth.dependencies import CurrentPrincipal

router = APIRouter(prefix="/api/v1/admin", tags=["administration"])


@router.get("/statistics", response_model=AdminStatisticsResponse)
def statistics(
    principal: CurrentPrincipal, service: AdminServiceDependency
) -> AdminStatisticsResponse:
    return service.statistics(principal)


@router.get("/audit-events", response_model=list[AuditEventResponse])
def audit_events(
    principal: CurrentPrincipal,
    service: AdminServiceDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[AuditEventResponse]:
    return [
        AuditEventResponse.model_validate(event) for event in service.audit_events(principal, limit)
    ]
