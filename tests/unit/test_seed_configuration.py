from __future__ import annotations

from opsdesk.auth.schemas import LoginRequest
from opsdesk.cli import SEED_USERS


def test_development_seed_addresses_are_accepted_by_login_schema() -> None:
    for email, _role, _password_setting in SEED_USERS:
        payload = LoginRequest(email=email, password="Development-Only-99!")
        assert str(payload.email) == email
