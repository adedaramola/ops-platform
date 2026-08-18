from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from opsdesk.db.models import AuditEvent, LoginThrottle, User, UserSession


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_user_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email))

    def find_user(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def add_user(self, user: User) -> None:
        self.session.add(user)

    def add_session(self, user_session: UserSession) -> None:
        self.session.add(user_session)

    def find_session_by_token_hash(self, token_hash: str) -> UserSession | None:
        return self.session.scalar(select(UserSession).where(UserSession.token_hash == token_hash))

    def find_throttle_for_update(self, key: str) -> LoginThrottle | None:
        return self.session.scalar(
            select(LoginThrottle).where(LoginThrottle.key == key).with_for_update()
        )

    def add_throttle(self, throttle: LoginThrottle) -> None:
        self.session.add(throttle)

    def clear_throttle(self, key: str) -> None:
        self.session.execute(delete(LoginThrottle).where(LoginThrottle.key == key))

    def add_audit(
        self,
        *,
        event_type: str,
        actor_user_id: uuid.UUID | None,
        request_id: str | None,
        trace_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AuditEvent(
                event_type=event_type,
                actor_user_id=actor_user_id,
                request_id=request_id,
                trace_id=trace_id,
                target_type=target_type,
                target_id=target_id,
                event_metadata=metadata or {},
            )
        )

    def delete_expired_sessions(self, before: datetime) -> None:
        self.session.execute(
            delete(UserSession).where(
                (UserSession.expires_at < before) | (UserSession.revoked_at.is_not(None))
            )
        )
