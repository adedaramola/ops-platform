from __future__ import annotations

from fastapi.testclient import TestClient
from httpx import Response

PASSWORD = "Correct-Horse-99!"


def csrf(client: TestClient) -> str:
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def register(
    client: TestClient, email: str = "person@example.com", password: str = PASSWORD
) -> Response:
    token = csrf(client)
    return client.post(
        "/api/v1/auth/register",
        headers={"X-CSRF-Token": token},
        json={"email": email, "password": password},
    )


def login(
    client: TestClient, email: str = "person@example.com", password: str = PASSWORD
) -> Response:
    token = csrf(client)
    return client.post(
        "/api/v1/auth/login",
        headers={"X-CSRF-Token": token},
        json={"email": email, "password": password},
    )
