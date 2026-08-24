from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opsdesk.ai.models import (
    AiOutboxEvent,
    AiReviewEvent,
    AiSuggestion,
    AiWorkflow,
    AiWorkflowStatus,
    ApprovalState,
    ReviewAction,
)
from opsdesk.ai.repository import AiRepository
from opsdesk.ai.schemas import AgentResult, AgentTicketContext, AiWorkflowResponse
from opsdesk.auth.repository import AuthRepository
from opsdesk.auth.service import AuthPrincipal
from opsdesk.core.config import Settings
from opsdesk.core.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from opsdesk.db.base import utc_now
from opsdesk.tickets.models import Comment, Ticket, TicketActivity
from opsdesk.tickets.repository import TicketRepository


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class AiWorkflowService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.repository = AiRepository(db)
        self.tickets = TicketRepository(db)
        self.audit = AuthRepository(db)

    def request_suggestion(
        self,
        principal: AuthPrincipal,
        ticket_id: uuid.UUID,
        suggestion_type: str,
        idempotency_key: str | None,
        request_id: str,
    ) -> AiWorkflow:
        if not self.settings.ai_enabled:
            raise ServiceUnavailableError(
                "AI suggestions are disabled; ticket operations remain available"
            )
        ticket = self._managed_ticket(principal, ticket_id)
        if idempotency_key:
            existing = self.repository.find_idempotent_workflow(principal.user.id, idempotency_key)
            if existing is not None:
                if existing.ticket_id != ticket.id or existing.workflow_type != suggestion_type:
                    raise ConflictError("That idempotency key was used for a different AI request")
                return existing
        now = utc_now()
        workflow = AiWorkflow(
            ticket_id=ticket.id,
            requested_by_id=principal.user.id,
            workflow_type=suggestion_type,
            status=AiWorkflowStatus.QUEUED,
            ticket_version=ticket.version,
            idempotency_key=idempotency_key,
            deadline_at=now + timedelta(seconds=self.settings.ai_workflow_deadline_seconds),
        )
        self.repository.add_workflow(workflow)
        self.db.flush()
        self.repository.add_outbox_event(AiOutboxEvent(workflow_id=workflow.id))
        self.tickets.add_activity(
            TicketActivity(
                ticket_id=ticket.id,
                actor_id=principal.user.id,
                event_type="ai_workflow.requested",
                event_metadata={"workflow_id": str(workflow.id), "type": suggestion_type},
            )
        )
        self.audit.add_audit(
            event_type="ai_workflow.requested",
            actor_user_id=principal.user.id,
            request_id=request_id,
            target_type="ai_workflow",
            target_id=str(workflow.id),
            metadata={"ticket_id": str(ticket.id), "type": suggestion_type},
        )
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            if idempotency_key:
                existing = self.repository.find_idempotent_workflow(
                    principal.user.id, idempotency_key
                )
                if existing is not None:
                    return existing
            raise ConflictError("The AI request could not be created") from error
        return workflow

    def get_workflow(self, principal: AuthPrincipal, workflow_id: uuid.UUID) -> AiWorkflow:
        workflow = self._workflow(workflow_id)
        self._managed_ticket(principal, workflow.ticket_id)
        return workflow

    def list_ticket_workflows(
        self, principal: AuthPrincipal, ticket_id: uuid.UUID
    ) -> Sequence[AiWorkflow]:
        self._managed_ticket(principal, ticket_id)
        return self.repository.list_ticket_workflows(ticket_id)

    def response(self, workflow: AiWorkflow) -> AiWorkflowResponse:
        suggestion = self.repository.get_workflow_suggestion(workflow.id)
        return AiWorkflowResponse(
            id=workflow.id,
            ticket_id=workflow.ticket_id,
            workflow_type=workflow.workflow_type,
            status=workflow.status,
            ticket_version=workflow.ticket_version,
            cancel_requested=workflow.cancel_requested,
            failure_code=workflow.failure_code,
            decision_summary=workflow.decision_summary,
            selected_tools=workflow.selected_tools,
            created_at=workflow.created_at,
            started_at=workflow.started_at,
            completed_at=workflow.completed_at,
            deadline_at=workflow.deadline_at,
            suggestion=suggestion,
        )

    def agent_context(self, workflow_id: uuid.UUID) -> AgentTicketContext:
        workflow = self._workflow(workflow_id)
        now = utc_now()
        if workflow.status == AiWorkflowStatus.CANCELLED or workflow.cancel_requested:
            raise ConflictError("AI workflow was cancelled")
        if workflow.status == AiWorkflowStatus.SUCCEEDED:
            pass
        elif workflow.status in {AiWorkflowStatus.QUEUED, AiWorkflowStatus.RUNNING}:
            if workflow.deadline_at <= now:
                workflow.status = AiWorkflowStatus.FAILED
                workflow.failure_code = "DEADLINE_EXCEEDED"
                workflow.completed_at = now
                self.db.commit()
                raise ConflictError("AI workflow deadline expired")
            if workflow.status == AiWorkflowStatus.QUEUED:
                workflow.status = AiWorkflowStatus.RUNNING
                workflow.started_at = now
                workflow.attempt_count += 1
                self.db.commit()
        else:
            raise ConflictError("AI workflow cannot be processed")
        ticket = self.tickets.get(workflow.ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found")
        # Internal notes and user identity are deliberately excluded from Agent context.
        comments = [item.body for item in self.tickets.list_comments(ticket.id)][:100]
        return AgentTicketContext(
            workflow_id=workflow.id,
            ticket_id=ticket.id,
            ticket_version=workflow.ticket_version,
            title=ticket.title,
            description=ticket.description,
            public_comments=comments,
            deadline_at=workflow.deadline_at,
            cancel_requested=workflow.cancel_requested,
        )

    def submit_result(self, workflow_id: uuid.UUID, result: AgentResult) -> AiWorkflow:
        workflow = self._workflow(workflow_id)
        existing = self.repository.get_workflow_suggestion(workflow.id)
        if workflow.status == AiWorkflowStatus.SUCCEEDED and existing is not None:
            return workflow
        if workflow.status not in {AiWorkflowStatus.QUEUED, AiWorkflowStatus.RUNNING}:
            raise ConflictError("AI workflow no longer accepts results")
        now = utc_now()
        if workflow.cancel_requested or workflow.deadline_at <= now:
            raise ConflictError("AI workflow was cancelled or expired")
        content = result.content.strip()
        suggestion = AiSuggestion(
            workflow_id=workflow.id,
            ticket_id=workflow.ticket_id,
            suggestion_type=result.suggestion_type,
            content=content,
            content_hash=_content_hash(content),
            citations=result.citations,
            rag_used=result.rag_used,
            provider_class=result.provider_class,
            model_class=result.model_class,
            generation_ms=result.generation_ms,
            estimated_cost_usd=result.estimated_cost_usd,
            gateway_request_id=result.gateway_request_id,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_policy=result.cache_policy,
            cache_source=result.cache_source,
            cache_hit=result.cache_hit,
        )
        self.repository.add_suggestion(suggestion)
        workflow.status = AiWorkflowStatus.SUCCEEDED
        workflow.decision_summary = result.decision_summary
        workflow.selected_tools = list(result.selected_tools)
        workflow.completed_at = now
        self.tickets.add_activity(
            TicketActivity(
                ticket_id=workflow.ticket_id,
                actor_id=None,
                event_type="ai_suggestion.generated",
                event_metadata={"workflow_id": str(workflow.id), "type": result.suggestion_type},
            )
        )
        self.audit.add_audit(
            event_type="ai_suggestion.generated",
            actor_user_id=None,
            request_id=None,
            target_type="ai_workflow",
            target_id=str(workflow.id),
            metadata={"type": result.suggestion_type},
        )
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.repository.get_workflow_suggestion(workflow.id)
            if existing is None:
                raise
        return self._workflow(workflow.id)

    def approve(
        self,
        principal: AuthPrincipal,
        suggestion_id: uuid.UUID,
        content: str | None,
        request_id: str,
    ) -> AiSuggestion:
        suggestion, workflow, ticket = self._reviewable(principal, suggestion_id)
        if suggestion.approval_state == ApprovalState.APPROVED:
            return suggestion
        if suggestion.approval_state != ApprovalState.PENDING:
            raise ConflictError("Only pending AI suggestions can be approved")
        self._require_current_ticket_version(workflow, ticket)
        if content is not None and content.strip() != suggestion.content:
            clean_content = content.strip()
            self._add_review_event(
                suggestion, principal, ticket, ReviewAction.EDITED, clean_content
            )
            suggestion.content = clean_content
            suggestion.content_hash = _content_hash(clean_content)
        suggestion.approval_state = ApprovalState.APPROVED
        suggestion.reviewed_by_id = principal.user.id
        suggestion.reviewed_at = utc_now()
        self._add_review_event(
            suggestion, principal, ticket, ReviewAction.APPROVED, suggestion.content
        )
        self._audit_review(principal, suggestion, request_id, "ai_suggestion.approved")
        self.db.commit()
        return suggestion

    def reject(
        self, principal: AuthPrincipal, suggestion_id: uuid.UUID, request_id: str
    ) -> AiSuggestion:
        suggestion, _workflow, ticket = self._reviewable(principal, suggestion_id)
        if suggestion.approval_state == ApprovalState.REJECTED:
            return suggestion
        if suggestion.approval_state != ApprovalState.PENDING:
            raise ConflictError("Only pending AI suggestions can be rejected")
        suggestion.approval_state = ApprovalState.REJECTED
        suggestion.reviewed_by_id = principal.user.id
        suggestion.reviewed_at = utc_now()
        self._add_review_event(
            suggestion, principal, ticket, ReviewAction.REJECTED, suggestion.content
        )
        self._audit_review(principal, suggestion, request_id, "ai_suggestion.rejected")
        self.db.commit()
        return suggestion

    def apply(
        self, principal: AuthPrincipal, suggestion_id: uuid.UUID, request_id: str
    ) -> tuple[AiSuggestion, Comment]:
        suggestion, workflow, ticket = self._reviewable(principal, suggestion_id)
        if suggestion.approval_state == ApprovalState.APPLIED:
            if suggestion.applied_comment_id is None:
                raise ConflictError("Applied AI suggestion is missing its comment")
            comment = self.db.get(Comment, suggestion.applied_comment_id)
            if comment is None:
                raise ConflictError("Applied AI suggestion comment was not found")
            return suggestion, comment
        if suggestion.approval_state != ApprovalState.APPROVED:
            raise ConflictError("AI suggestion must be approved before it can be applied")
        self._require_current_ticket_version(workflow, ticket)
        comment = Comment(
            ticket_id=ticket.id,
            author_id=principal.user.id,
            body=suggestion.content,
        )
        self.tickets.add_comment(comment)
        self.db.flush()
        suggestion.approval_state = ApprovalState.APPLIED
        suggestion.applied_at = utc_now()
        suggestion.applied_comment_id = comment.id
        self._add_review_event(
            suggestion, principal, ticket, ReviewAction.APPLIED, suggestion.content
        )
        self.tickets.add_activity(
            TicketActivity(
                ticket_id=ticket.id,
                actor_id=principal.user.id,
                event_type="ai_suggestion.applied",
                event_metadata={
                    "suggestion_id": str(suggestion.id),
                    "comment_id": str(comment.id),
                },
            )
        )
        self._audit_review(principal, suggestion, request_id, "ai_suggestion.applied")
        self.db.commit()
        return suggestion, comment

    def _reviewable(
        self, principal: AuthPrincipal, suggestion_id: uuid.UUID
    ) -> tuple[AiSuggestion, AiWorkflow, Ticket]:
        suggestion = self.repository.get_suggestion(suggestion_id)
        if suggestion is None:
            raise NotFoundError("AI suggestion not found")
        workflow = self._workflow(suggestion.workflow_id)
        ticket = self._managed_ticket(principal, workflow.ticket_id)
        return suggestion, workflow, ticket

    def _workflow(self, workflow_id: uuid.UUID) -> AiWorkflow:
        workflow = self.repository.get_workflow(workflow_id)
        if workflow is None:
            raise NotFoundError("AI workflow not found")
        return workflow

    def _managed_ticket(self, principal: AuthPrincipal, ticket_id: uuid.UUID) -> Ticket:
        ticket = self.tickets.get(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found")
        if principal.user.role_key == "admin" or (
            principal.user.role_key == "agent" and ticket.assignee_id == principal.user.id
        ):
            return ticket
        raise AuthorizationError()

    @staticmethod
    def _require_current_ticket_version(workflow: AiWorkflow, ticket: Ticket) -> None:
        if ticket.version != workflow.ticket_version:
            raise ConflictError("AI suggestion is stale because the ticket changed")

    def _add_review_event(
        self,
        suggestion: AiSuggestion,
        principal: AuthPrincipal,
        ticket: Ticket,
        action: ReviewAction,
        content: str,
    ) -> None:
        self.repository.add_review_event(
            AiReviewEvent(
                suggestion_id=suggestion.id,
                actor_id=principal.user.id,
                action=action,
                ticket_version=ticket.version,
                content_hash=_content_hash(content),
                content_snapshot=content,
            )
        )

    def _audit_review(
        self,
        principal: AuthPrincipal,
        suggestion: AiSuggestion,
        request_id: str,
        event_type: str,
    ) -> None:
        self.audit.add_audit(
            event_type=event_type,
            actor_user_id=principal.user.id,
            request_id=request_id,
            target_type="ai_suggestion",
            target_id=str(suggestion.id),
        )
