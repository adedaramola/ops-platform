from __future__ import annotations

from opsdesk.auth.service import AuthPrincipal
from opsdesk.core.errors import AuthorizationError


def require_role(principal: AuthPrincipal, *allowed_roles: str) -> None:
    if principal.user.role_key not in allowed_roles:
        raise AuthorizationError()
