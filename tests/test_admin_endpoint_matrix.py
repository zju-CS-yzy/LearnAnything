"""Authorization matrix for every system-administrator HTTP endpoint."""

from dataclasses import dataclass

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import app.auth as auth
from app.backend_api import app
from core.user_manager import UserManager


@dataclass(frozen=True)
class AdminEndpoint:
    method: str
    path: str
    body: dict | None = None
    route_path: str | None = None


ADMIN_ENDPOINTS = (
    AdminEndpoint("GET", "/api/setup/config"),
    AdminEndpoint("POST", "/api/setup/config", {}),
    AdminEndpoint(
        "POST",
        "/api/setup/test/llm",
        {},
        "/api/setup/test/{feature}",
    ),
    AdminEndpoint("GET", "/api/config"),
    AdminEndpoint("PUT", "/api/config", {}),
    AdminEndpoint("GET", "/api/llm/diagnostic"),
    AdminEndpoint("POST", "/api/llm/test", {}),
    AdminEndpoint("GET", "/api/llm/usage/stats"),
    AdminEndpoint("GET", "/api/llm/usage/daily"),
    AdminEndpoint("GET", "/api/llm/usage/models"),
    AdminEndpoint(
        "POST",
        "/api/llm/usage/budget",
        {"monthly_budget": 10, "warning_threshold": 0.8},
    ),
    AdminEndpoint("GET", "/api/llm/usage/budget"),
    AdminEndpoint("GET", "/api/llm/slow-requests"),
    AdminEndpoint("GET", "/api/llm/slow-requests/stats"),
    AdminEndpoint("GET", "/api/llm/slow-requests/models"),
    AdminEndpoint("GET", "/api/admin/users"),
    AdminEndpoint(
        "POST",
        "/api/admin/users/matrix-target/role",
        {"role": "admin", "current_password": "admin-pass"},
        "/api/admin/users/{target_user_id}/role",
    ),
)


@pytest.fixture()
def authorization_matrix(tmp_path, monkeypatch):
    manager = UserManager(tmp_path / "users")
    regular = manager.create_user("matrix_regular", "regular-pass")
    administrator = manager.create_user("matrix_admin", "admin-pass")
    manager.set_system_role(administrator["user_id"], "admin")
    monkeypatch.setattr(auth, "get_user_manager", lambda: manager)

    return {
        "regular": {
            "Authorization": f"Bearer {manager.generate_token(regular['user_id'])}"
        },
        "admin": {
            "Authorization": (
                f"Bearer {manager.generate_token(administrator['user_id'])}"
            )
        },
        "admin_id": administrator["user_id"],
    }


def _request(client: TestClient, endpoint: AdminEndpoint, headers=None):
    kwargs = {"headers": headers or {}}
    if endpoint.body is not None:
        kwargs["json"] = endpoint.body
    return client.request(endpoint.method, endpoint.path, **kwargs)


def _dependency_calls(route: APIRoute):
    pending = list(route.dependant.dependencies)
    while pending:
        dependency = pending.pop()
        yield dependency.call
        pending.extend(dependency.dependencies)


@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
def test_admin_endpoint_matrix_rejects_anonymous_and_regular_users(
    endpoint,
    authorization_matrix,
):
    client = TestClient(app)

    assert _request(client, endpoint).status_code == 401
    assert (
        _request(client, endpoint, authorization_matrix["regular"]).status_code
        == 403
    )


@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
def test_admin_endpoint_matrix_is_wired_to_shared_admin_dependency(endpoint):
    route_path = endpoint.route_path or endpoint.path
    matching_routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == route_path
        and endpoint.method in route.methods
    ]

    assert len(matching_routes) == 1
    assert auth.require_admin in set(_dependency_calls(matching_routes[0]))


def test_shared_admin_dependency_accepts_an_administrator(authorization_matrix):
    assert auth.require_admin(
        x_user_id=None,
        authorization=authorization_matrix["admin"]["Authorization"],
    ) == authorization_matrix["admin_id"]
