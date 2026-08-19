from __future__ import annotations

from fastapi.testclient import TestClient


def test_openapi_exposes_phase3_routes_security_and_error_schema(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    expected_paths = {
        "/api/v1/users",
        "/api/v1/categories",
        "/api/v1/tickets",
        "/api/v1/tickets/{ticket_id}",
        "/api/v1/tickets/{ticket_id}/comments",
        "/api/v1/tickets/{ticket_id}/internal-notes",
        "/api/v1/tickets/{ticket_id}/activity",
        "/api/v1/tickets/{ticket_id}/assignment",
        "/api/v1/tickets/{ticket_id}/status",
        "/api/v1/tickets/{ticket_id}/priority",
        "/api/v1/tickets/{ticket_id}/category",
        "/api/v1/dashboard",
        "/api/v1/admin/statistics",
        "/api/v1/admin/audit-events",
    }
    assert expected_paths <= document["paths"].keys()
    assert document["components"]["securitySchemes"]["APIKeyCookie"]["in"] == "cookie"
    assert "ErrorResponse" in document["components"]["schemas"]
    ticket_operation = document["paths"]["/api/v1/tickets"]["get"]
    assert {"APIKeyCookie": []} in ticket_operation["security"]
    assert "403" in ticket_operation["responses"]
    assert "409" in document["paths"]["/api/v1/tickets/{ticket_id}/status"]["post"]["responses"]
