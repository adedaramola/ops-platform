from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import ColumnElement, Select, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from opsdesk.db.base import utc_now
from opsdesk.tickets.models import Comment, InternalNote, Ticket, TicketActivity

TICKET_NUMBER_PATTERN = re.compile(r"^(?:OPS-)?0*(\d+)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TicketFilters:
    query: str | None = None
    status: str | None = None
    priority: str | None = None
    category_id: uuid.UUID | None = None
    requester_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    unassigned: bool = False


class TicketRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, ticket: Ticket) -> None:
        self.session.add(ticket)

    def get(self, ticket_id: uuid.UUID) -> Ticket | None:
        return self.session.get(Ticket, ticket_id)

    def list(
        self,
        *,
        requester_scope: uuid.UUID | None,
        filters: TicketFilters,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[Ticket], int]:
        statement = select(Ticket)
        if requester_scope is not None:
            statement = statement.where(Ticket.requester_id == requester_scope)
        statement = self._apply_filters(statement, filters)
        total = self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        statement = statement.order_by(Ticket.created_at.desc(), Ticket.id.desc())
        statement = statement.offset((page - 1) * page_size).limit(page_size)
        return list(self.session.scalars(statement)), total

    def update_versioned(
        self, ticket_id: uuid.UUID, expected_version: int, values: dict[str, Any]
    ) -> bool:
        statement = (
            update(Ticket)
            .where(Ticket.id == ticket_id, Ticket.version == expected_version)
            .values(
                **values,
                version=Ticket.version + 1,
                updated_at=utc_now(),
            )
            .execution_options(synchronize_session=False)
        )
        result = cast(CursorResult[Any], self.session.execute(statement))
        return bool(result.rowcount)

    def add_comment(self, comment: Comment) -> None:
        self.session.add(comment)

    def list_comments(self, ticket_id: uuid.UUID) -> Sequence[Comment]:
        return list(
            self.session.scalars(
                select(Comment)
                .where(Comment.ticket_id == ticket_id)
                .order_by(Comment.created_at, Comment.id)
            )
        )

    def add_internal_note(self, note: InternalNote) -> None:
        self.session.add(note)

    def list_internal_notes(self, ticket_id: uuid.UUID) -> Sequence[InternalNote]:
        return list(
            self.session.scalars(
                select(InternalNote)
                .where(InternalNote.ticket_id == ticket_id)
                .order_by(InternalNote.created_at, InternalNote.id)
            )
        )

    def add_activity(self, activity: TicketActivity) -> None:
        self.session.add(activity)

    def list_activity(
        self, ticket_id: uuid.UUID, *, include_internal: bool
    ) -> Sequence[TicketActivity]:
        statement = select(TicketActivity).where(TicketActivity.ticket_id == ticket_id)
        if not include_internal:
            statement = statement.where(TicketActivity.event_type != "internal_note.created")
        return list(
            self.session.scalars(statement.order_by(TicketActivity.created_at, TicketActivity.id))
        )

    def dashboard_counts(
        self, *, requester_scope: uuid.UUID | None, principal_id: uuid.UUID
    ) -> tuple[dict[str, int], int, int, int]:
        scope = [] if requester_scope is None else [Ticket.requester_id == requester_scope]
        rows = self.session.execute(
            select(Ticket.status, func.count()).where(*scope).group_by(Ticket.status)
        ).all()
        counts = {str(status): int(count) for status, count in rows}
        total = sum(counts.values())
        unassigned = (
            self.session.scalar(
                select(func.count()).select_from(Ticket).where(*scope, Ticket.assignee_id.is_(None))
            )
            or 0
        )
        assigned_to_me = (
            self.session.scalar(
                select(func.count())
                .select_from(Ticket)
                .where(*scope, Ticket.assignee_id == principal_id)
            )
            or 0
        )
        return counts, total, int(unassigned), int(assigned_to_me)

    def _apply_filters(
        self, statement: Select[tuple[Ticket]], filters: TicketFilters
    ) -> Select[tuple[Ticket]]:
        if filters.query:
            query = filters.query.strip()
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            criteria: list[ColumnElement[bool]] = [Ticket.title.ilike(f"%{escaped}%", escape="\\")]
            match = TICKET_NUMBER_PATTERN.fullmatch(query)
            if match:
                criteria.append(Ticket.ticket_number == int(match.group(1)))
            statement = statement.where(or_(*criteria))
        if filters.status:
            statement = statement.where(Ticket.status == filters.status)
        if filters.priority:
            statement = statement.where(Ticket.priority == filters.priority)
        if filters.category_id:
            statement = statement.where(Ticket.category_id == filters.category_id)
        if filters.requester_id:
            statement = statement.where(Ticket.requester_id == filters.requester_id)
        if filters.assignee_id:
            statement = statement.where(Ticket.assignee_id == filters.assignee_id)
        if filters.unassigned:
            statement = statement.where(Ticket.assignee_id.is_(None))
        return statement
