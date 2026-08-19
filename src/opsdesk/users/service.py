from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from opsdesk.auth.authorization import require_role
from opsdesk.auth.repository import AuthRepository
from opsdesk.auth.service import AuthPrincipal
from opsdesk.core.errors import NotFoundError, WorkflowError
from opsdesk.db.models import User
from opsdesk.observability.logging import get_logger
from opsdesk.users.repository import UserRepository


class UserAdminService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = UserRepository(db)
        self.audit = AuthRepository(db)

    def list(self, principal: AuthPrincipal) -> list[User]:
        require_role(principal, "admin")
        return self.repository.list()

    def set_role(
        self, principal: AuthPrincipal, user_id: uuid.UUID, role: str, request_id: str
    ) -> User:
        require_role(principal, "admin")
        if role not in {"user", "agent", "admin"}:
            raise WorkflowError("Unknown user role")
        target = self._target(user_id)
        if target.id == principal.user.id and role != "admin":
            raise WorkflowError("Administrators cannot remove their own administrator role")
        previous = target.role_key
        target.role_key = role
        self.audit.add_audit(
            event_type="admin.user_role_changed",
            actor_user_id=principal.user.id,
            request_id=request_id,
            target_type="user",
            target_id=str(target.id),
            metadata={"from": previous, "to": role},
        )
        self.db.commit()
        get_logger().info(
            "admin.user_role_changed",
            event_name="admin.user_role_changed",
            target_user_id=str(target.id),
        )
        return target

    def set_active(
        self, principal: AuthPrincipal, user_id: uuid.UUID, is_active: bool, request_id: str
    ) -> User:
        require_role(principal, "admin")
        target = self._target(user_id)
        if target.id == principal.user.id and not is_active:
            raise WorkflowError("Administrators cannot deactivate their own account")
        target.is_active = is_active
        self.audit.add_audit(
            event_type="admin.user_activation_changed",
            actor_user_id=principal.user.id,
            request_id=request_id,
            target_type="user",
            target_id=str(target.id),
            metadata={"is_active": is_active},
        )
        self.db.commit()
        get_logger().info(
            "admin.user_activation_changed",
            event_name="admin.user_activation_changed",
            target_user_id=str(target.id),
            is_active=is_active,
        )
        return target

    def _target(self, user_id: uuid.UUID) -> User:
        user = self.repository.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user
