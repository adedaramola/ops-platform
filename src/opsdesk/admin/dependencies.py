from typing import Annotated

from fastapi import Depends

from opsdesk.admin.service import AdminService
from opsdesk.auth.dependencies import DatabaseSession


def get_admin_service(db: DatabaseSession) -> AdminService:
    return AdminService(db)


AdminServiceDependency = Annotated[AdminService, Depends(get_admin_service)]
