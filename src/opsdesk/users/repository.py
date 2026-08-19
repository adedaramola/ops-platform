from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from opsdesk.db.models import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[User]:
        return list(self.session.scalars(select(User).order_by(User.created_at, User.id)))

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)
