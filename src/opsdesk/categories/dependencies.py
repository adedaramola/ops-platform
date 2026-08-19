from typing import Annotated

from fastapi import Depends

from opsdesk.auth.dependencies import DatabaseSession
from opsdesk.categories.service import CategoryService


def get_category_service(db: DatabaseSession) -> CategoryService:
    return CategoryService(db)


CategoryServiceDependency = Annotated[CategoryService, Depends(get_category_service)]
