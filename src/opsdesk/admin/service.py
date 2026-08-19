from __future__ import annotations

from sqlalchemy.orm import Session

from opsdesk.admin.repository import AdminRepository
from opsdesk.admin.schemas import AdminStatisticsResponse
from opsdesk.auth.authorization import require_role
from opsdesk.auth.service import AuthPrincipal
from opsdesk.db.models import AuditEvent


class AdminService:
    def __init__(self, db: Session) -> None:
        self.repository = AdminRepository(db)

    def audit_events(self, principal: AuthPrincipal, limit: int) -> list[AuditEvent]:
        require_role(principal, "admin")
        return self.repository.audit_events(limit)

    def statistics(self, principal: AuthPrincipal) -> AdminStatisticsResponse:
        require_role(principal, "admin")
        return AdminStatisticsResponse.model_validate(self.repository.statistics())
