from __future__ import annotations

import re

from tests.phase3_helpers import ActorFactory, create_ticket

TOKEN_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def token_from(html: str) -> str:
    match = TOKEN_PATTERN.search(html)
    assert match is not None
    return match.group(1)


def test_browser_ticket_creation_comment_and_private_note_privacy(
    actor_factory: ActorFactory,
) -> None:
    requester = actor_factory("requester@example.com", "user")
    agent = actor_factory("agent@example.com", "agent")

    new_page = requester.client.get("/tickets/new")
    create_response = requester.client.post(
        "/tickets",
        data={
            "title": "Browser-created ticket",
            "description": "Created through the server-rendered workflow",
            "category_id": "00000000-0000-0000-0000-000000000001",
            "priority": "high",
            "csrf_token": token_from(new_page.text),
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 303
    detail_path = create_response.headers["location"]
    detail = requester.client.get(detail_path)
    comment_response = requester.client.post(
        f"{detail_path}/comments",
        data={"body": "Browser public comment", "csrf_token": token_from(detail.text)},
        follow_redirects=False,
    )

    agent_detail = agent.client.get(detail_path)
    note_response = agent.client.post(
        f"{detail_path}/internal-notes",
        data={"body": "BROWSER-PRIVATE-MARKER", "csrf_token": token_from(agent_detail.text)},
        follow_redirects=False,
    )
    requester_detail = requester.client.get(detail_path)
    staff_detail = agent.client.get(detail_path)

    assert new_page.status_code == 200
    assert create_response.status_code == 303
    assert comment_response.status_code == 303
    assert note_response.status_code == 303
    assert "Browser-created ticket" in requester_detail.text
    assert "Browser public comment" in requester_detail.text
    assert "BROWSER-PRIVATE-MARKER" not in requester_detail.text
    assert "Private internal notes" not in requester_detail.text
    assert "BROWSER-PRIVATE-MARKER" in staff_detail.text


def test_browser_and_api_have_equivalent_cross_user_denial(actor_factory: ActorFactory) -> None:
    owner = actor_factory("owner@example.com", "user")
    outsider = actor_factory("outsider@example.com", "user")
    ticket = create_ticket(owner)

    browser = outsider.client.get(f"/tickets/{ticket['id']}")
    api = outsider.client.get(f"/api/v1/tickets/{ticket['id']}")

    assert browser.status_code == api.status_code == 404
    assert "PRIVATE" not in browser.text


def test_htmx_ticket_search_and_admin_browser(actor_factory: ActorFactory) -> None:
    user = actor_factory("user@example.com", "user")
    admin = actor_factory("admin@example.com", "admin")
    create_ticket(user, title="HTMX searchable ticket")

    search = user.client.get("/tickets", params={"query": "HTMX"}, headers={"HX-Request": "true"})
    denied_admin = user.client.get("/admin")
    admin_page = admin.client.get("/admin")
    category_response = admin.client.post(
        "/admin/categories",
        data={
            "name": "Software",
            "description": "Applications",
            "csrf_token": token_from(admin_page.text),
        },
        follow_redirects=False,
    )
    refreshed = admin.client.get("/admin")

    assert search.status_code == 200
    assert "HTMX searchable ticket" in search.text
    assert denied_admin.status_code == 403
    assert admin_page.status_code == 200
    assert category_response.status_code == 303
    assert "Software" in refreshed.text
