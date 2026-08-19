from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from opsdesk.categories.models import Category


class CategoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, *, include_inactive: bool) -> list[Category]:
        statement = select(Category)
        if not include_inactive:
            statement = statement.where(Category.is_active.is_(True))
        return list(self.session.scalars(statement.order_by(Category.name, Category.id)))

    def get(self, category_id: uuid.UUID) -> Category | None:
        return self.session.get(Category, category_id)

    def get_by_name(self, name: str) -> Category | None:
        return self.session.scalar(select(Category).where(Category.name == name))

    def add(self, category: Category) -> None:
        self.session.add(category)
