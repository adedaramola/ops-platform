from __future__ import annotations

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from opsdesk.categories.models import Category
from opsdesk.db.models import AuditEvent, User
from opsdesk.tickets.models import Ticket


class AdminRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def audit_events(self, limit: int) -> list[AuditEvent]:
        return list(
            self.session.scalars(
                select(AuditEvent)
                .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                .limit(limit)
            )
        )

    def statistics(self) -> dict[str, object]:
        users_total = self._count(User)
        users_active = self._count(User, User.is_active.is_(True))
        categories_total = self._count(Category)
        categories_active = self._count(Category, Category.is_active.is_(True))
        tickets_total = self._count(Ticket)
        tickets_unassigned = self._count(Ticket, Ticket.assignee_id.is_(None))
        status_counts = {
            str(key): int(value)
            for key, value in self.session.execute(
                select(Ticket.status, func.count()).group_by(Ticket.status)
            ).all()
        }
        priority_counts = {
            str(key): int(value)
            for key, value in self.session.execute(
                select(Ticket.priority, func.count()).group_by(Ticket.priority)
            ).all()
        }
        return {
            "users_total": users_total,
            "users_active": users_active,
            "categories_total": categories_total,
            "categories_active": categories_active,
            "tickets_total": tickets_total,
            "tickets_unassigned": tickets_unassigned,
            "status_counts": status_counts,
            "priority_counts": priority_counts,
        }

    def _count(self, model: type[object], *criteria: ColumnElement[bool]) -> int:
        value = self.session.scalar(select(func.count()).select_from(model).where(*criteria))
        return int(value or 0)
