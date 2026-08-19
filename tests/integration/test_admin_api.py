from __future__ import annotations

from tests.helpers import csrf
from tests.phase3_helpers import ActorFactory, create_ticket


def test_admin_user_category_statistics_and_audit_operations(
    actor_factory: ActorFactory,
) -> None:
    admin = actor_factory("admin@example.com", "admin")
    target = actor_factory("target@example.com", "user")
    regular = actor_factory("regular@example.com", "user")
    create_ticket(regular)

    assert regular.client.get("/api/v1/users").status_code == 403
    assert regular.client.get("/api/v1/admin/statistics").status_code == 403

    admin_token = csrf(admin.client)
    users = admin.client.get("/api/v1/users")
    role_change = admin.client.patch(
        f"/api/v1/users/{target.user.id}/role",
        headers={"X-CSRF-Token": admin_token},
        json={"role": "agent"},
    )
    admin_token = csrf(admin.client)
    activation_change = admin.client.patch(
        f"/api/v1/users/{target.user.id}/activation",
        headers={"X-CSRF-Token": admin_token},
        json={"is_active": False},
    )
    admin_token = csrf(admin.client)
    category = admin.client.post(
        "/api/v1/categories",
        headers={"X-CSRF-Token": admin_token},
        json={"name": "Hardware", "description": "Physical devices"},
    )
    admin_token = csrf(admin.client)
    deactivated_category = admin.client.patch(
        f"/api/v1/categories/{category.json()['id']}",
        headers={"X-CSRF-Token": admin_token},
        json={"is_active": False},
    )
    token = csrf(regular.client)
    inactive_category_ticket = regular.client.post(
        "/api/v1/tickets",
        headers={"X-CSRF-Token": token},
        json={
            "title": "Cannot use retired category",
            "description": "This request must be rejected.",
            "category_id": category.json()["id"],
            "priority": "medium",
        },
    )

    statistics = admin.client.get("/api/v1/admin/statistics")
    audit = admin.client.get("/api/v1/admin/audit-events")
    regular_categories = regular.client.get("/api/v1/categories")
    admin_categories = admin.client.get("/api/v1/categories")

    assert users.status_code == 200 and len(users.json()) == 3
    assert "password" not in users.text
    assert role_change.status_code == 200 and role_change.json()["role_key"] == "agent"
    assert activation_change.status_code == 200
    assert activation_change.json()["is_active"] is False
    assert target.client.get("/api/v1/auth/status").json()["authenticated"] is False
    assert category.status_code == 201
    assert deactivated_category.status_code == 200
    assert inactive_category_ticket.status_code == 422
    assert statistics.status_code == 200
    assert statistics.json()["tickets_total"] == 1
    assert statistics.json()["tickets_unassigned"] == 1
    assert statistics.json()["status_counts"] == {"open": 1}
    assert audit.status_code == 200
    assert "admin.user_role_changed" in audit.text
    assert "admin.category_updated" in audit.text
    assert "Hardware" not in audit.text
    assert all(item["name"] != "Hardware" for item in regular_categories.json())
    assert any(item["name"] == "Hardware" for item in admin_categories.json())


def test_admin_cannot_lock_out_own_account(actor_factory: ActorFactory) -> None:
    admin = actor_factory("admin@example.com", "admin")
    token = csrf(admin.client)
    demote = admin.client.patch(
        f"/api/v1/users/{admin.user.id}/role",
        headers={"X-CSRF-Token": token},
        json={"role": "user"},
    )
    token = csrf(admin.client)
    deactivate = admin.client.patch(
        f"/api/v1/users/{admin.user.id}/activation",
        headers={"X-CSRF-Token": token},
        json={"is_active": False},
    )
    assert demote.status_code == 422
    assert deactivate.status_code == 422
