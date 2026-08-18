from __future__ import annotations

import sys

from sqlalchemy.orm import Session

from opsdesk.auth.repository import AuthRepository
from opsdesk.auth.security import get_password_service, normalize_email
from opsdesk.core.config import get_settings
from opsdesk.db.models import User
from opsdesk.db.session import get_session_factory

SEED_USERS = (
    ("demo-user@opsdesk.local", "user", "seed_user_password"),
    ("demo-agent@opsdesk.local", "agent", "seed_agent_password"),
    ("demo-admin@opsdesk.local", "admin", "seed_admin_password"),
)


def _seed(session: Session) -> int:
    settings = get_settings()
    if settings.environment != "development" or not settings.enable_dev_seed:
        raise RuntimeError(
            "Development seeding requires development mode and OPS_ENABLE_DEV_SEED=true"
        )
    repository = AuthRepository(session)
    passwords = get_password_service()
    created = 0
    for email, role, password_setting in SEED_USERS:
        if repository.find_user_by_email(normalize_email(email)) is not None:
            continue
        secret = getattr(settings, password_setting)
        if secret is None or not secret.get_secret_value():
            raise RuntimeError(f"{password_setting.upper()} is required when seeding")
        repository.add_user(
            User(
                email=normalize_email(email),
                password_hash=passwords.hash(secret.get_secret_value()),
                role_key=role,
                is_active=True,
            )
        )
        created += 1
    session.commit()
    return created


def seed_dev_data() -> None:
    session = get_session_factory()()
    try:
        created = _seed(session)
    except Exception as error:
        session.rollback()
        print(f"Seed failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    finally:
        session.close()
    print(f"Development seed complete; created {created} account(s).")


if __name__ == "__main__":
    seed_dev_data()
