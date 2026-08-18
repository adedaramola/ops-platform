from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from opsdesk.db.base import utc_now
from opsdesk.db.models import AuditEvent, User, UserSession
from opsdesk.db.session import get_session_factory
from tests.helpers import PASSWORD, csrf, login, register


def test_registration_hashes_password_and_audits(client: TestClient) -> None:
    response = register(client, email="Person@Example.com")

    assert response.status_code == 201
    assert response.json()["role"] == "user"
    assert "email" not in response.json()
    with get_session_factory()() as session:
        user = session.scalar(select(User).where(User.email == "person@example.com"))
        assert user is not None
        assert user.password_hash != PASSWORD
        event = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "user.registered"))
        assert event is not None


def test_duplicate_registration_uses_safe_conflict(client: TestClient) -> None:
    assert register(client).status_code == 201
    response = register(client)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    assert "person@example.com" not in response.text


def test_login_status_and_logout_flow(client: TestClient) -> None:
    assert register(client).status_code == 201
    response = login(client)

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert "opsdesk_session" in response.cookies
    assert response.cookies.get("opsdesk_session")
    session_cookie = next(
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith("opsdesk_session=")
    )
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Path=/" in session_cookie
    assert "Max-Age=28800" in session_cookie
    assert client.get("/api/v1/auth/status").json()["authenticated"] is True

    token = csrf(client)
    logout_response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": token})
    assert logout_response.status_code == 204
    assert client.get("/api/v1/auth/status").json()["authenticated"] is False
    with get_session_factory()() as session:
        stored = session.scalar(select(UserSession))
        assert stored is not None and stored.revoked_at is not None


def test_each_login_rotates_the_session_token(client: TestClient) -> None:
    assert register(client).status_code == 201
    first = login(client)
    first_token = first.cookies.get("opsdesk_session")
    second = login(client)
    second_token = second.cookies.get("opsdesk_session")

    assert first_token
    assert second_token
    assert first_token != second_token
    with get_session_factory()() as session:
        assert session.scalar(select(func.count()).select_from(UserSession)) == 2


def test_invalid_login_is_generic_and_audited(client: TestClient) -> None:
    response = login(client, email="missing@example.com", password="wrong")

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Unable to authenticate"
    assert "missing@example.com" not in response.text
    with get_session_factory()() as session:
        count = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "user.login_failed")
        )
        assert count == 1


def test_login_rate_limit_persists(client: TestClient) -> None:
    for _ in range(5):
        assert login(client, email="missing@example.com", password="wrong").status_code == 401

    blocked = login(client, email="missing@example.com", password="wrong")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_inactive_user_cannot_login(client: TestClient) -> None:
    assert register(client).status_code == 201
    with get_session_factory()() as session:
        user = session.scalar(select(User).where(User.email == "person@example.com"))
        assert user is not None
        user.is_active = False
        session.commit()

    response = login(client)
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Unable to authenticate"


def test_expired_idle_and_revoked_sessions_are_rejected(client: TestClient) -> None:
    assert register(client).status_code == 201
    assert login(client).status_code == 200
    with get_session_factory()() as session:
        stored = session.scalar(select(UserSession))
        assert stored is not None
        stored.expires_at = utc_now() - timedelta(seconds=1)
        session.commit()

    assert client.get("/api/v1/auth/status").json()["authenticated"] is False

    assert login(client).status_code == 200
    with get_session_factory()() as session:
        stored = session.scalars(
            select(UserSession).order_by(UserSession.created_at.desc())
        ).first()
        assert stored is not None
        stored.last_seen_at = utc_now() - timedelta(minutes=61)
        session.commit()

    assert client.get("/api/v1/auth/status").json()["authenticated"] is False

    assert login(client).status_code == 200
    with get_session_factory()() as session:
        stored = session.scalars(
            select(UserSession).order_by(UserSession.created_at.desc())
        ).first()
        assert stored is not None
        stored.revoked_at = utc_now()
        session.commit()

    assert client.get("/api/v1/auth/status").json()["authenticated"] is False


def test_valid_htmx_registration_is_accepted(client: TestClient) -> None:
    token = csrf(client)
    response = client.post(
        "/api/v1/auth/register",
        headers={"X-CSRF-Token": token, "HX-Request": "true"},
        json={"email": "htmx@example.com", "password": PASSWORD},
    )

    assert response.status_code == 201


def test_csrf_is_required_and_bound_to_cookie(client: TestClient) -> None:
    token = csrf(client)
    missing = client.post(
        "/api/v1/auth/register",
        json={"email": "person@example.com", "password": PASSWORD},
    )
    tampered = client.post(
        "/api/v1/auth/register",
        headers={"X-CSRF-Token": f"{token}tampered"},
        json={"email": "person@example.com", "password": PASSWORD},
    )

    assert missing.status_code == 422
    assert tampered.status_code == 403


def test_validation_error_does_not_echo_password(client: TestClient) -> None:
    token = csrf(client)
    response = client.post(
        "/api/v1/auth/register",
        headers={"X-CSRF-Token": token},
        json={"email": "invalid", "password": "SensitivePassword!99"},
    )

    assert response.status_code == 422
    assert "SensitivePassword!99" not in response.text
