from typing import Annotated

from fastapi import Depends

from opsdesk.auth.dependencies import DatabaseSession
from opsdesk.users.service import UserAdminService


def get_user_admin_service(db: DatabaseSession) -> UserAdminService:
    return UserAdminService(db)


UserAdminServiceDependency = Annotated[UserAdminService, Depends(get_user_admin_service)]
