from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from opsdesk.ai.dependencies import AiServiceDependency, AuthenticatedAgent
from opsdesk.ai.schemas import (
    AgentResult,
    AgentTicketContext,
    AiSuggestionRequest,
    AiSuggestionResponse,
    AiWorkflowResponse,
    ApplyResponse,
    ApprovalCommand,
)
from opsdesk.auth.dependencies import AppSettings, CurrentPrincipal
from opsdesk.auth.http import validate_csrf
from opsdesk.observability.middleware import get_request_id, get_traceparent
from opsdesk.tickets.api import CsrfHeader

router = APIRouter(tags=["AI workflows"])
internal_router = APIRouter(prefix="/internal/v1/ai-workflows", tags=["Agent service"])


@router.post(
    "/api/v1/tickets/{ticket_id}/ai-suggestions",
    response_model=AiWorkflowResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_ai_suggestion(
    ticket_id: uuid.UUID,
    payload: AiSuggestionRequest,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: AiServiceDependency,
) -> AiWorkflowResponse:
    validate_csrf(request, csrf_token, settings, principal)
    workflow = service.request_suggestion(
        principal,
        ticket_id,
        payload.suggestion_type,
        payload.idempotency_key,
        get_request_id(request),
        get_traceparent(request),
    )
    return service.response(workflow)


@router.get("/api/v1/ai-workflows/{workflow_id}", response_model=AiWorkflowResponse)
def get_ai_workflow(
    workflow_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: AiServiceDependency,
) -> AiWorkflowResponse:
    return service.response(service.get_workflow(principal, workflow_id))


@router.post(
    "/api/v1/ai-suggestions/{suggestion_id}/approve",
    response_model=AiSuggestionResponse,
)
def approve_ai_suggestion(
    suggestion_id: uuid.UUID,
    payload: ApprovalCommand,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: AiServiceDependency,
) -> AiSuggestionResponse:
    validate_csrf(request, csrf_token, settings, principal)
    return AiSuggestionResponse.model_validate(
        service.approve(principal, suggestion_id, payload.content, get_request_id(request))
    )


@router.post(
    "/api/v1/ai-suggestions/{suggestion_id}/reject",
    response_model=AiSuggestionResponse,
)
def reject_ai_suggestion(
    suggestion_id: uuid.UUID,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: AiServiceDependency,
) -> AiSuggestionResponse:
    validate_csrf(request, csrf_token, settings, principal)
    return AiSuggestionResponse.model_validate(
        service.reject(principal, suggestion_id, get_request_id(request))
    )


@router.post(
    "/api/v1/ai-suggestions/{suggestion_id}/apply",
    response_model=ApplyResponse,
)
def apply_ai_suggestion(
    suggestion_id: uuid.UUID,
    request: Request,
    csrf_token: CsrfHeader,
    settings: AppSettings,
    principal: CurrentPrincipal,
    service: AiServiceDependency,
) -> ApplyResponse:
    validate_csrf(request, csrf_token, settings, principal)
    suggestion, comment = service.apply(principal, suggestion_id, get_request_id(request))
    return ApplyResponse(
        suggestion_id=suggestion.id,
        approval_state="applied",
        comment_id=comment.id,
    )


@internal_router.get("/{workflow_id}/context", response_model=AgentTicketContext)
def agent_workflow_context(
    workflow_id: uuid.UUID,
    _authenticated: AuthenticatedAgent,
    service: AiServiceDependency,
) -> AgentTicketContext:
    return service.agent_context(workflow_id)


@internal_router.post("/{workflow_id}/result", response_model=AiWorkflowResponse)
def submit_agent_result(
    workflow_id: uuid.UUID,
    payload: AgentResult,
    _authenticated: AuthenticatedAgent,
    service: AiServiceDependency,
) -> AiWorkflowResponse:
    return service.response(service.submit_result(workflow_id, payload))
