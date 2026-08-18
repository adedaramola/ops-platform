from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from opsdesk.auth.authorization import require_role
from opsdesk.auth.service import AuthPrincipal
from opsdesk.core.errors import AuthorizationError
from opsdesk.db.base import utc_now
from opsdesk.db.models import User, UserSession


def principal(role: str) -> AuthPrincipal:
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="hidden@example.test",
        password_hash="hidden",
        role_key=role,
        is_active=True,
    )
    session = UserSession(
        user_id=user_id,
        token_hash="a" * 64,
        csrf_secret="secret",
        expires_at=utc_now() + timedelta(hours=1),
        user=user,
    )
    return AuthPrincipal(user=user, session=session)


def test_require_role_allows_matching_role() -> None:
    require_role(principal("admin"), "admin")


def test_require_role_rejects_other_role() -> None:
    with pytest.raises(AuthorizationError):
        require_role(principal("user"), "agent", "admin")
