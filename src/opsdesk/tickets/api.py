from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, status

from opsdesk.auth.dependencies import AppSettings, CurrentPrincipal
from opsdesk.auth.http import validate_csrf
from opsdesk.observability.middleware import get_request_id
from opsdesk.tickets.dependencies import TicketServiceDependency
from opsdesk.tickets.models import TicketPriority, TicketStatus
from opsdesk.tickets.repository import TicketFilters
from opsdesk.tickets.schemas import (
    ActivityResponse,
    AssignmentCommand,
    CategoryCommand,
    CommentCreate,
    CommentResponse,
    DashboardResponse,
    InternalNoteCreate,
    InternalNoteResponse,
    PriorityCommand,
    StatusCommand,
    TicketCreate,
    TicketDetailResponse,
    TicketListResponse,
    TicketResponse,
    ticket_response,
)

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])
dashboard_router = APIRouter(prefix="/api/v1", tags=["dashboard"])
CsrfHeader = Annotated[str, Header(alias="X-CSRF-Token", min_length=1, max_length=256)]


@router.get("", response_model=TicketListResponse)
def list_tickets(
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
    query: Annotated[str | None, Query(max_length=200)] = None,
    ticket_status: Annotated[TicketStatus | None, Query(alias="status")] = None,
    priority: TicketPriority | None = None,
    category_id: uuid.UUID | None = None,
    requester_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
    unassigned: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> TicketListResponse:
    filters = TicketFilters(
        query=query,
        status=ticket_status,
        priority=priority,
        category_id=category_id,
        requester_id=requester_id,
        assignee_id=assignee_id,
        unassigned=unassigned,
    )
    tickets, total = service.list(principal, filters, page, page_size)
    return TicketListResponse(
        items=[ticket_response(ticket) for ticket in tickets],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
) -> TicketResponse:
    validate_csrf(request, csrf_token, settings, principal)
    ticket = service.create(principal, payload, get_request_id(request))
    return ticket_response(ticket)


@router.get("/{ticket_id}", response_model=TicketDetailResponse)
def get_ticket(
    ticket_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
) -> TicketDetailResponse:
    ticket = service.get(principal, ticket_id)
    return TicketDetailResponse(
        ticket=ticket_response(ticket),
        comments=[
            CommentResponse.model_validate(item) for item in service.comments(principal, ticket_id)
        ],
        activity=[
            ActivityResponse.model_validate(item) for item in service.activity(principal, ticket_id)
        ],
    )


@router.get("/{ticket_id}/comments", response_model=list[CommentResponse])
def list_comments(
    ticket_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
) -> list[CommentResponse]:
    return [CommentResponse.model_validate(item) for item in service.comments(principal, ticket_id)]


@router.post(
    "/{ticket_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_comment(
    ticket_id: uuid.UUID,
    payload: CommentCreate,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
) -> CommentResponse:
    validate_csrf(request, csrf_token, settings, principal)
    comment = service.add_comment(principal, ticket_id, payload.body, get_request_id(request))
    return CommentResponse.model_validate(comment)


@router.get("/{ticket_id}/internal-notes", response_model=list[InternalNoteResponse])
def list_internal_notes(
    ticket_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
) -> list[InternalNoteResponse]:
    return [
        InternalNoteResponse.model_validate(item)
        for item in service.internal_notes(principal, ticket_id)
    ]


@router.post(
    "/{ticket_id}/internal-notes",
    response_model=InternalNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_internal_note(
    ticket_id: uuid.UUID,
    payload: InternalNoteCreate,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
) -> InternalNoteResponse:
    validate_csrf(request, csrf_token, settings, principal)
    note = service.add_internal_note(principal, ticket_id, payload.body, get_request_id(request))
    return InternalNoteResponse.model_validate(note)


@router.get("/{ticket_id}/activity", response_model=list[ActivityResponse])
def list_activity(
    ticket_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
) -> list[ActivityResponse]:
    return [
        ActivityResponse.model_validate(item) for item in service.activity(principal, ticket_id)
    ]


@router.post("/{ticket_id}/assignment", response_model=TicketResponse)
def assign_ticket(
    ticket_id: uuid.UUID,
    payload: AssignmentCommand,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
) -> TicketResponse:
    validate_csrf(request, csrf_token, settings, principal)
    ticket = service.assign(
        principal,
        ticket_id,
        payload.assignee_id,
        payload.expected_version,
        get_request_id(request),
    )
    return ticket_response(ticket)


@router.post("/{ticket_id}/status", response_model=TicketResponse)
def change_ticket_status(
    ticket_id: uuid.UUID,
    payload: StatusCommand,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
) -> TicketResponse:
    validate_csrf(request, csrf_token, settings, principal)
    ticket = service.change_status(
        principal,
        ticket_id,
        payload.status,
        payload.expected_version,
        get_request_id(request),
    )
    return ticket_response(ticket)


@router.post("/{ticket_id}/priority", response_model=TicketResponse)
def change_ticket_priority(
    ticket_id: uuid.UUID,
    payload: PriorityCommand,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
) -> TicketResponse:
    validate_csrf(request, csrf_token, settings, principal)
    ticket = service.change_priority(
        principal,
        ticket_id,
        payload.priority,
        payload.expected_version,
        get_request_id(request),
    )
    return ticket_response(ticket)


@router.post("/{ticket_id}/category", response_model=TicketResponse)
def change_ticket_category(
    ticket_id: uuid.UUID,
    payload: CategoryCommand,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
) -> TicketResponse:
    validate_csrf(request, csrf_token, settings, principal)
    ticket = service.change_category(
        principal,
        ticket_id,
        payload.category_id,
        payload.expected_version,
        get_request_id(request),
    )
    return ticket_response(ticket)


@dashboard_router.get("/dashboard", response_model=DashboardResponse)
def dashboard(principal: CurrentPrincipal, service: TicketServiceDependency) -> DashboardResponse:
    return service.dashboard(principal)
