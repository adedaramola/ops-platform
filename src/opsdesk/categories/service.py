from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opsdesk.auth.authorization import require_role
from opsdesk.auth.repository import AuthRepository
from opsdesk.auth.service import AuthPrincipal
from opsdesk.categories.models import Category
from opsdesk.categories.repository import CategoryRepository
from opsdesk.categories.schemas import CategoryCreate, CategoryUpdate
from opsdesk.core.errors import ConflictError, NotFoundError, WorkflowError
from opsdesk.observability.logging import get_logger


class CategoryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CategoryRepository(db)
        self.audit = AuthRepository(db)

    def list(self, principal: AuthPrincipal) -> list[Category]:
        return self.repository.list(include_inactive=principal.user.role_key == "admin")

    def get_active(self, category_id: uuid.UUID) -> Category:
        category = self.repository.get(category_id)
        if category is None:
            raise NotFoundError("Category not found")
        if not category.is_active:
            raise WorkflowError("The selected category is inactive")
        return category

    def create(
        self, principal: AuthPrincipal, payload: CategoryCreate, request_id: str
    ) -> Category:
        require_role(principal, "admin")
        name = payload.name.strip()
        if self.repository.get_by_name(name) is not None:
            raise ConflictError("A category with that name already exists")
        category = Category(name=name, description=payload.description.strip(), is_active=True)
        self.repository.add(category)
        try:
            self.db.flush()
            self.audit.add_audit(
                event_type="admin.category_created",
                actor_user_id=principal.user.id,
                request_id=request_id,
                target_type="category",
                target_id=str(category.id),
            )
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise ConflictError("A category with that name already exists") from error
        get_logger().info(
            "category.created", event_name="category.created", category_id=str(category.id)
        )
        return category

    def update(
        self,
        principal: AuthPrincipal,
        category_id: uuid.UUID,
        payload: CategoryUpdate,
        request_id: str,
    ) -> Category:
        require_role(principal, "admin")
        category = self.repository.get(category_id)
        if category is None:
            raise NotFoundError("Category not found")
        changed_fields: list[str] = []
        if payload.name is not None:
            category.name = payload.name.strip()
            changed_fields.append("name")
        if payload.description is not None:
            category.description = payload.description.strip()
            changed_fields.append("description")
        if payload.is_active is not None:
            category.is_active = payload.is_active
            changed_fields.append("is_active")
        if not changed_fields:
            raise WorkflowError("At least one category field must be changed")
        self.audit.add_audit(
            event_type="admin.category_updated",
            actor_user_id=principal.user.id,
            request_id=request_id,
            target_type="category",
            target_id=str(category.id),
            metadata={"changed_fields": changed_fields},
        )
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise ConflictError("A category with that name already exists") from error
        get_logger().info(
            "category.updated", event_name="category.updated", category_id=str(category.id)
        )
        return category
