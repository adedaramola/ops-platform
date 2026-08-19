from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from opsdesk.auth.repository import AuthRepository
from opsdesk.auth.service import AuthPrincipal
from opsdesk.categories.service import CategoryService
from opsdesk.core.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    WorkflowError,
)
from opsdesk.db.base import utc_now
from opsdesk.db.models import User
from opsdesk.observability.logging import get_logger
from opsdesk.tickets.models import (
    Comment,
    InternalNote,
    Ticket,
    TicketActivity,
    TicketStatus,
)
from opsdesk.tickets.repository import TicketFilters, TicketRepository
from opsdesk.tickets.schemas import DashboardResponse, TicketCreate
from opsdesk.users.repository import UserRepository

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    TicketStatus.OPEN: frozenset(
        {TicketStatus.IN_PROGRESS, TicketStatus.WAITING_FOR_USER, TicketStatus.RESOLVED}
    ),
    TicketStatus.IN_PROGRESS: frozenset(
        {TicketStatus.OPEN, TicketStatus.WAITING_FOR_USER, TicketStatus.RESOLVED}
    ),
    TicketStatus.WAITING_FOR_USER: frozenset(
        {TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED}
    ),
    TicketStatus.RESOLVED: frozenset({TicketStatus.OPEN, TicketStatus.CLOSED}),
    TicketStatus.CLOSED: frozenset({TicketStatus.OPEN}),
}


class TicketService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = TicketRepository(db)
        self.categories = CategoryService(db)
        self.users = UserRepository(db)
        self.audit = AuthRepository(db)

    def create(
        self,
        principal: AuthPrincipal,
        payload: TicketCreate,
        request_id: str,
    ) -> Ticket:
        self.categories.get_active(payload.category_id)
        ticket = Ticket(
            title=payload.title.strip(),
            description=payload.description.strip(),
            category_id=payload.category_id,
            requester_id=principal.user.id,
            priority=payload.priority,
            status=TicketStatus.OPEN,
            version=1,
        )
        if not ticket.description:
            raise WorkflowError("Ticket description cannot be empty")
        self.repository.add(ticket)
        self.db.flush()
        self._add_activity(ticket, principal, "ticket.created", {"priority": ticket.priority})
        self._add_audit(ticket, principal, request_id, "ticket.created")
        self.db.commit()
        get_logger().info(
            "ticket.created",
            event_name="ticket.created",
            ticket_id=str(ticket.id),
            priority=ticket.priority,
        )
        return ticket

    def list(
        self,
        principal: AuthPrincipal,
        filters: TicketFilters,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[Ticket], int]:
        self._authorize_filters(principal, filters)
        requester_scope = principal.user.id if principal.user.role_key == "user" else None
        tickets, total = self.repository.list(
            requester_scope=requester_scope,
            filters=filters,
            page=page,
            page_size=page_size,
        )
        get_logger().info(
            "search.executed",
            event_name="search.executed",
            has_query=bool(filters.query),
            has_status_filter=bool(filters.status),
            has_priority_filter=bool(filters.priority),
            has_category_filter=filters.category_id is not None,
            page=page,
            result_count=len(tickets),
        )
        return tickets, total

    def get(self, principal: AuthPrincipal, ticket_id: uuid.UUID) -> Ticket:
        ticket = self.repository.get(ticket_id)
        if ticket is None or not self._can_view(principal, ticket):
            raise NotFoundError("Ticket not found")
        return ticket

    def comments(self, principal: AuthPrincipal, ticket_id: uuid.UUID) -> Sequence[Comment]:
        self.get(principal, ticket_id)
        return self.repository.list_comments(ticket_id)

    def activity(self, principal: AuthPrincipal, ticket_id: uuid.UUID) -> Sequence[TicketActivity]:
        self.get(principal, ticket_id)
        return self.repository.list_activity(
            ticket_id, include_internal=principal.user.role_key in {"agent", "admin"}
        )

    def add_comment(
        self,
        principal: AuthPrincipal,
        ticket_id: uuid.UUID,
        body: str,
        request_id: str,
    ) -> Comment:
        ticket = self.get(principal, ticket_id)
        clean_body = body.strip()
        if not clean_body:
            raise WorkflowError("Comment cannot be empty")
        comment = Comment(ticket_id=ticket.id, author_id=principal.user.id, body=clean_body)
        self.repository.add_comment(comment)
        self.db.flush()
        self._add_activity(ticket, principal, "comment.created", {"comment_id": str(comment.id)})
        self._add_audit(ticket, principal, request_id, "comment.created")
        self.db.commit()
        get_logger().info(
            "comment.created",
            event_name="comment.created",
            ticket_id=str(ticket.id),
            comment_id=str(comment.id),
        )
        return comment

    def internal_notes(
        self, principal: AuthPrincipal, ticket_id: uuid.UUID
    ) -> Sequence[InternalNote]:
        self._require_staff(principal)
        self.get(principal, ticket_id)
        return self.repository.list_internal_notes(ticket_id)

    def add_internal_note(
        self,
        principal: AuthPrincipal,
        ticket_id: uuid.UUID,
        body: str,
        request_id: str,
    ) -> InternalNote:
        self._require_staff(principal)
        ticket = self.get(principal, ticket_id)
        clean_body = body.strip()
        if not clean_body:
            raise WorkflowError("Internal note cannot be empty")
        note = InternalNote(ticket_id=ticket.id, author_id=principal.user.id, body=clean_body)
        self.repository.add_internal_note(note)
        self.db.flush()
        self._add_activity(
            ticket, principal, "internal_note.created", {"internal_note_id": str(note.id)}
        )
        self._add_audit(ticket, principal, request_id, "internal_note.created")
        self.db.commit()
        get_logger().info(
            "internal_note.created",
            event_name="internal_note.created",
            ticket_id=str(ticket.id),
            internal_note_id=str(note.id),
        )
        return note

    def assign(
        self,
        principal: AuthPrincipal,
        ticket_id: uuid.UUID,
        assignee_id: uuid.UUID | None,
        expected_version: int,
        request_id: str,
    ) -> Ticket:
        ticket = self.get(principal, ticket_id)
        if principal.user.role_key == "agent":
            if ticket.assignee_id is not None or assignee_id != principal.user.id:
                raise AuthorizationError()
        elif principal.user.role_key != "admin":
            raise AuthorizationError()
        if assignee_id is not None:
            assignee = self.users.get(assignee_id)
            if assignee is None or assignee.role_key != "agent" or not assignee.is_active:
                raise WorkflowError("Tickets can only be assigned to an active support agent")
        previous = ticket.assignee_id
        return self._versioned_change(
            ticket,
            principal,
            expected_version,
            {"assignee_id": assignee_id},
            "ticket.assigned",
            {"from_assignee_id": self._id(previous), "to_assignee_id": self._id(assignee_id)},
            request_id,
        )

    def change_status(
        self,
        principal: AuthPrincipal,
        ticket_id: uuid.UUID,
        new_status: str,
        expected_version: int,
        request_id: str,
    ) -> Ticket:
        ticket = self.get(principal, ticket_id)
        if new_status not in ALLOWED_TRANSITIONS.get(ticket.status, frozenset()):
            raise WorkflowError(f"Cannot transition ticket from {ticket.status} to {new_status}")
        is_reopen = new_status == TicketStatus.OPEN and ticket.status in {
            TicketStatus.RESOLVED,
            TicketStatus.CLOSED,
        }
        if is_reopen and ticket.requester_id == principal.user.id:
            pass
        elif not self._can_manage_ticket(principal, ticket):
            raise AuthorizationError()
        values: dict[str, Any] = {"status": new_status}
        if new_status == TicketStatus.RESOLVED:
            values.update(resolved_at=utc_now(), closed_at=None)
        elif new_status == TicketStatus.CLOSED:
            values["closed_at"] = utc_now()
        elif is_reopen:
            values.update(resolved_at=None, closed_at=None)
        return self._versioned_change(
            ticket,
            principal,
            expected_version,
            values,
            "ticket.status_changed",
            {"from": ticket.status, "to": new_status},
            request_id,
        )

    def change_priority(
        self,
        principal: AuthPrincipal,
        ticket_id: uuid.UUID,
        new_priority: str,
        expected_version: int,
        request_id: str,
    ) -> Ticket:
        ticket = self.get(principal, ticket_id)
        if not self._can_manage_ticket(principal, ticket):
            raise AuthorizationError()
        if ticket.priority == new_priority:
            raise WorkflowError("Ticket already has that priority")
        return self._versioned_change(
            ticket,
            principal,
            expected_version,
            {"priority": new_priority},
            "ticket.priority_changed",
            {"from": ticket.priority, "to": new_priority},
            request_id,
        )

    def change_category(
        self,
        principal: AuthPrincipal,
        ticket_id: uuid.UUID,
        category_id: uuid.UUID,
        expected_version: int,
        request_id: str,
    ) -> Ticket:
        ticket = self.get(principal, ticket_id)
        if not self._can_manage_ticket(principal, ticket):
            raise AuthorizationError()
        self.categories.get_active(category_id)
        if ticket.category_id == category_id:
            raise WorkflowError("Ticket already has that category")
        return self._versioned_change(
            ticket,
            principal,
            expected_version,
            {"category_id": category_id},
            "ticket.category_changed",
            {"from_category_id": str(ticket.category_id), "to_category_id": str(category_id)},
            request_id,
        )

    def dashboard(self, principal: AuthPrincipal) -> DashboardResponse:
        requester_scope = principal.user.id if principal.user.role_key == "user" else None
        counts, total, unassigned, assigned = self.repository.dashboard_counts(
            requester_scope=requester_scope, principal_id=principal.user.id
        )
        return DashboardResponse(
            role=principal.user.role_key,
            status_counts=counts,
            total_visible=total,
            unassigned=unassigned if principal.user.role_key != "user" else 0,
            assigned_to_me=assigned if principal.user.role_key != "user" else 0,
        )

    def assignable_agents(self, principal: AuthPrincipal) -> Sequence[User]:
        if principal.user.role_key != "admin":
            return ()
        return tuple(
            user for user in self.users.list() if user.role_key == "agent" and user.is_active
        )

    def _versioned_change(
        self,
        ticket: Ticket,
        principal: AuthPrincipal,
        expected_version: int,
        values: dict[str, Any],
        event_type: str,
        metadata: dict[str, Any],
        request_id: str,
    ) -> Ticket:
        if not self.repository.update_versioned(ticket.id, expected_version, values):
            self.db.rollback()
            raise ConflictError("Ticket was changed by another request; refresh and try again")
        self.db.expire_all()
        updated = self.repository.get(ticket.id)
        if updated is None:
            self.db.rollback()
            raise NotFoundError("Ticket not found")
        self._add_activity(updated, principal, event_type, metadata)
        self._add_audit(updated, principal, request_id, event_type, metadata)
        self.db.commit()
        get_logger().info(
            event_type,
            event_name=event_type,
            ticket_id=str(updated.id),
        )
        return updated

    def _add_activity(
        self,
        ticket: Ticket,
        principal: AuthPrincipal,
        event_type: str,
        metadata: dict[str, Any],
    ) -> None:
        self.repository.add_activity(
            TicketActivity(
                ticket_id=ticket.id,
                actor_id=principal.user.id,
                event_type=event_type,
                event_metadata=metadata,
            )
        )

    def _add_audit(
        self,
        ticket: Ticket,
        principal: AuthPrincipal,
        request_id: str,
        event_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.audit.add_audit(
            event_type=event_type,
            actor_user_id=principal.user.id,
            request_id=request_id,
            target_type="ticket",
            target_id=str(ticket.id),
            metadata=metadata,
        )

    def _authorize_filters(self, principal: AuthPrincipal, filters: TicketFilters) -> None:
        if principal.user.role_key != "user":
            return
        if filters.requester_id not in {None, principal.user.id}:
            raise AuthorizationError()
        if filters.assignee_id is not None or filters.unassigned:
            raise AuthorizationError()

    @staticmethod
    def _can_view(principal: AuthPrincipal, ticket: Ticket) -> bool:
        return principal.user.role_key in {"agent", "admin"} or (
            ticket.requester_id == principal.user.id
        )

    @staticmethod
    def _can_manage_ticket(principal: AuthPrincipal, ticket: Ticket) -> bool:
        return principal.user.role_key == "admin" or (
            principal.user.role_key == "agent" and ticket.assignee_id == principal.user.id
        )

    @staticmethod
    def _require_staff(principal: AuthPrincipal) -> None:
        if principal.user.role_key not in {"agent", "admin"}:
            raise AuthorizationError()

    @staticmethod
    def _id(value: uuid.UUID | None) -> str | None:
        return str(value) if value is not None else None
