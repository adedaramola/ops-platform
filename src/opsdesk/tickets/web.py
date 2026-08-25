from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from opsdesk.ai.dependencies import AiServiceDependency
from opsdesk.auth.dependencies import AppSettings, CurrentPrincipal
from opsdesk.auth.http import set_csrf_cookie, validate_csrf
from opsdesk.auth.security import get_csrf_manager
from opsdesk.categories.dependencies import CategoryServiceDependency
from opsdesk.core.errors import AppError
from opsdesk.observability.middleware import get_request_id
from opsdesk.tickets.dependencies import TicketServiceDependency
from opsdesk.tickets.models import TicketPriority, TicketStatus
from opsdesk.tickets.repository import TicketFilters
from opsdesk.tickets.schemas import TicketCreate
from opsdesk.web.templates import templates

router = APIRouter(tags=["ticket browser"])


def _set_csrf_cookie(response: Response, settings: AppSettings, token: str) -> Response:
    set_csrf_cookie(response, settings, token)
    return response


@router.get("/tickets", response_class=HTMLResponse)
def ticket_list_page(
    request: Request,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
    category_service: CategoryServiceDependency,
    query: Annotated[str | None, Query(max_length=200)] = None,
    ticket_status: Annotated[TicketStatus | None, Query(alias="status")] = None,
    priority: TicketPriority | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
) -> Response:
    tickets, total = service.list(
        principal,
        TicketFilters(query=query, status=ticket_status, priority=priority),
        page,
        25,
    )
    return templates.TemplateResponse(
        request=request,
        name="tickets/list.html",
        context={
            "principal": principal,
            "tickets": tickets,
            "categories": category_service.list(principal),
            "dashboard": service.dashboard(principal),
            "query": query or "",
            "selected_status": ticket_status or "",
            "selected_priority": priority or "",
            "page": page,
            "total": total,
        },
    )


@router.get("/tickets/new", response_class=HTMLResponse)
def new_ticket_page(
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    category_service: CategoryServiceDependency,
) -> Response:
    token = get_csrf_manager().issue(principal.session.csrf_secret)
    response = templates.TemplateResponse(
        request=request,
        name="tickets/new.html",
        context={
            "principal": principal,
            "categories": category_service.list(principal),
            "error": None,
            "csrf_token": token,
        },
    )
    return _set_csrf_cookie(response, settings, token)


@router.post("/tickets", response_class=HTMLResponse)
def create_ticket_submit(
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
    category_service: CategoryServiceDependency,
    title: Annotated[str, Form(max_length=200)],
    description: Annotated[str, Form(max_length=20_000)],
    category_id: Annotated[uuid.UUID, Form()],
    priority: Annotated[TicketPriority, Form()],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> Response:
    try:
        validate_csrf(request, csrf_token, settings, principal)
        ticket = service.create(
            principal,
            TicketCreate(
                title=title,
                description=description,
                category_id=category_id,
                priority=priority,
            ),
            get_request_id(request),
        )
    except (AppError, ValidationError) as error:
        message = error.message if isinstance(error, AppError) else "Ticket details are invalid"
        token = get_csrf_manager().issue(principal.session.csrf_secret)
        response = templates.TemplateResponse(
            request=request,
            name="tickets/new.html",
            context={
                "principal": principal,
                "categories": category_service.list(principal),
                "error": message,
                "csrf_token": token,
            },
            status_code=getattr(error, "status_code", status.HTTP_422_UNPROCESSABLE_CONTENT),
        )
        return _set_csrf_cookie(response, settings, token)
    return RedirectResponse(f"/tickets/{ticket.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_detail_page(
    ticket_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
    category_service: CategoryServiceDependency,
    ai_service: AiServiceDependency,
) -> Response:
    ticket = service.get(principal, ticket_id)
    token = get_csrf_manager().issue(principal.session.csrf_secret)
    can_manage = principal.user.role_key == "admin" or (
        principal.user.role_key == "agent" and ticket.assignee_id == principal.user.id
    )
    response = templates.TemplateResponse(
        request=request,
        name="tickets/detail.html",
        context={
            "principal": principal,
            "ticket": ticket,
            "comments": service.comments(principal, ticket_id),
            "activity": service.activity(principal, ticket_id),
            "internal_notes": (
                service.internal_notes(principal, ticket_id)
                if principal.user.role_key in {"agent", "admin"}
                else ()
            ),
            "categories": category_service.list(principal),
            "agents": service.assignable_agents(principal),
            "can_manage": can_manage,
            "ai_enabled": settings.ai_enabled,
            "ai_workflows": (
                [
                    ai_service.response(workflow)
                    for workflow in ai_service.list_ticket_workflows(principal, ticket_id)
                ]
                if can_manage
                else []
            ),
            "csrf_token": token,
        },
    )
    return _set_csrf_cookie(response, settings, token)


@router.post("/tickets/{ticket_id}/ai-suggestions")
def ai_suggestion_submit(
    ticket_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: AiServiceDependency,
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    service.request_suggestion(
        principal,
        ticket_id,
        "draft_public_response",
        None,
        get_request_id(request),
    )
    return _ticket_redirect(ticket_id)


@router.post("/tickets/{ticket_id}/ai-suggestions/{suggestion_id}/approve")
def ai_suggestion_approve_submit(
    ticket_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: AiServiceDependency,
    content: Annotated[str, Form(min_length=1, max_length=10_000)],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    service.approve(principal, suggestion_id, content, get_request_id(request))
    return _ticket_redirect(ticket_id)


@router.post("/tickets/{ticket_id}/ai-suggestions/{suggestion_id}/reject")
def ai_suggestion_reject_submit(
    ticket_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: AiServiceDependency,
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    service.reject(principal, suggestion_id, get_request_id(request))
    return _ticket_redirect(ticket_id)


@router.post("/tickets/{ticket_id}/ai-suggestions/{suggestion_id}/apply")
def ai_suggestion_apply_submit(
    ticket_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: AiServiceDependency,
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    service.apply(principal, suggestion_id, get_request_id(request))
    return _ticket_redirect(ticket_id)


@router.post("/tickets/{ticket_id}/comments")
def comment_submit(
    ticket_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
    body: Annotated[str, Form(max_length=10_000)],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    service.add_comment(principal, ticket_id, body, get_request_id(request))
    return _ticket_redirect(ticket_id)


@router.post("/tickets/{ticket_id}/internal-notes")
def internal_note_submit(
    ticket_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
    body: Annotated[str, Form(max_length=10_000)],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    service.add_internal_note(principal, ticket_id, body, get_request_id(request))
    return _ticket_redirect(ticket_id)


@router.post("/tickets/{ticket_id}/assignment")
def assignment_submit(
    ticket_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
    assignee_id: Annotated[uuid.UUID, Form()],
    expected_version: Annotated[int, Form(gt=0)],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    service.assign(principal, ticket_id, assignee_id, expected_version, get_request_id(request))
    return _ticket_redirect(ticket_id)


@router.post("/tickets/{ticket_id}/status")
def status_submit(
    ticket_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
    ticket_status: Annotated[TicketStatus, Form(alias="status")],
    expected_version: Annotated[int, Form(gt=0)],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    service.change_status(
        principal,
        ticket_id,
        ticket_status,
        expected_version,
        get_request_id(request),
    )
    return _ticket_redirect(ticket_id)


@router.post("/tickets/{ticket_id}/priority")
def priority_submit(
    ticket_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
    priority: Annotated[TicketPriority, Form()],
    expected_version: Annotated[int, Form(gt=0)],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    service.change_priority(
        principal, ticket_id, priority, expected_version, get_request_id(request)
    )
    return _ticket_redirect(ticket_id)


@router.post("/tickets/{ticket_id}/category")
def category_submit(
    ticket_id: uuid.UUID,
    request: Request,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: TicketServiceDependency,
    category_id: Annotated[uuid.UUID, Form()],
    expected_version: Annotated[int, Form(gt=0)],
    csrf_token: Annotated[str, Form(min_length=1, max_length=256)],
) -> RedirectResponse:
    validate_csrf(request, csrf_token, settings, principal)
    service.change_category(
        principal,
        ticket_id,
        category_id,
        expected_version,
        get_request_id(request),
    )
    return _ticket_redirect(ticket_id)


def _ticket_redirect(ticket_id: uuid.UUID) -> RedirectResponse:
    return RedirectResponse(f"/tickets/{ticket_id}", status_code=status.HTTP_303_SEE_OTHER)
