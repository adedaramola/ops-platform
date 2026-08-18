from __future__ import annotations

import re

from fastapi.testclient import TestClient

from tests.helpers import PASSWORD

TOKEN_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def form_token(response_text: str) -> str:
    match = TOKEN_PATTERN.search(response_text)
    assert match is not None
    return match.group(1)


def test_browser_registration_login_and_logout(client: TestClient) -> None:
    register_page = client.get("/register")
    assert register_page.status_code == 200
    assert "Create an account" in register_page.text
    register_response = client.post(
        "/register",
        data={
            "email": "browser@example.com",
            "password": PASSWORD,
            "csrf_token": form_token(register_page.text),
        },
        follow_redirects=False,
    )
    assert register_response.status_code == 303

    login_page = client.get("/login")
    login_response = client.post(
        "/login",
        data={
            "email": "browser@example.com",
            "password": PASSWORD,
            "csrf_token": form_token(login_page.text),
        },
        follow_redirects=False,
    )
    assert login_response.status_code == 303
    assert login_response.headers["location"] == "/account"

    account_page = client.get("/account")
    assert account_page.status_code == 200
    assert "browser@example.com" in account_page.text
    logout_response = client.post(
        "/logout",
        data={"csrf_token": form_token(account_page.text)},
        follow_redirects=False,
    )
    assert logout_response.status_code == 303
    assert logout_response.headers["location"] == "/login"


def test_browser_form_rejects_invalid_csrf(client: TestClient) -> None:
    response = client.post(
        "/register",
        data={
            "email": "browser@example.com",
            "password": PASSWORD,
            "csrf_token": "invalid",
        },
    )
    assert response.status_code == 403
    assert "form security token is invalid" in response.text
