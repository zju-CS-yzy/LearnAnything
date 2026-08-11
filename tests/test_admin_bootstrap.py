"""Tests for local first-administrator bootstrap and role management."""

import json
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.admin_api as admin_api
import app.auth as auth
from core.user_manager import UserManager


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def bootstrap_state(tmp_path, monkeypatch):
    manager = UserManager(tmp_path / "data")
    first = manager.create_user("first_user", "first-pass")
    second = manager.create_user("second_user", "second-pass")
    first_token = manager.generate_token(first["user_id"])
    second_token = manager.generate_token(second["user_id"])
    audit_path = tmp_path / "admin_audit.jsonl"

    monkeypatch.setattr(auth, "get_user_manager", lambda: manager)
    monkeypatch.setattr(admin_api, "get_user_manager", lambda: manager)
    monkeypatch.setattr(admin_api, "AUDIT_LOG_PATH", audit_path)
    monkeypatch.setattr(admin_api, "_is_loopback_request", lambda request: True)
    admin_api._bootstrap_failures.clear()

    api = FastAPI()
    api.include_router(admin_api.router)
    return {
        "manager": manager,
        "first": first,
        "second": second,
        "first_headers": _bearer(first_token),
        "second_headers": _bearer(second_token),
        "audit_path": audit_path,
        "client": TestClient(api),
    }


def test_local_password_user_can_claim_the_only_initial_admin(bootstrap_state):
    client = bootstrap_state["client"]
    manager = bootstrap_state["manager"]

    status = client.get("/api/admin/bootstrap/status")
    assert status.status_code == 200
    assert status.json() == {
        "bootstrap_required": True,
        "can_claim_locally": True,
    }

    response = client.post(
        "/api/admin/bootstrap/claim",
        headers=bootstrap_state["first_headers"],
        json={"password": "first-pass"},
    )
    assert response.status_code == 200
    assert manager.get_system_role(bootstrap_state["first"]["user_id"]) == "admin"
    assert manager.count_system_admins() == 1

    status = client.get("/api/admin/bootstrap/status").json()
    assert status["bootstrap_required"] is False
    assert status["can_claim_locally"] is False

    audit_text = bootstrap_state["audit_path"].read_text(encoding="utf-8")
    assert "admin.bootstrap.claim" in audit_text
    assert "first-pass" not in audit_text


def test_bootstrap_rejects_remote_anonymous_wrong_password_and_repeat_claim(
    bootstrap_state,
    monkeypatch,
):
    client = bootstrap_state["client"]

    assert client.post(
        "/api/admin/bootstrap/claim", json={"password": "first-pass"}
    ).status_code == 401

    monkeypatch.setattr(admin_api, "_is_loopback_request", lambda request: False)
    assert client.post(
        "/api/admin/bootstrap/claim",
        headers=bootstrap_state["first_headers"],
        json={"password": "first-pass"},
    ).status_code == 403

    monkeypatch.setattr(admin_api, "_is_loopback_request", lambda request: True)
    assert client.post(
        "/api/admin/bootstrap/claim",
        headers=bootstrap_state["first_headers"],
        json={"password": "wrong-password"},
    ).status_code == 401

    assert client.post(
        "/api/admin/bootstrap/claim",
        headers=bootstrap_state["first_headers"],
        json={"password": "first-pass"},
    ).status_code == 200

    repeated = client.post(
        "/api/admin/bootstrap/claim",
        headers=bootstrap_state["second_headers"],
        json={"password": "second-pass"},
    )
    assert repeated.status_code == 409


def test_bootstrap_password_failures_are_rate_limited(bootstrap_state):
    client = bootstrap_state["client"]
    for _ in range(admin_api._BOOTSTRAP_FAILURE_LIMIT):
        response = client.post(
            "/api/admin/bootstrap/claim",
            headers=bootstrap_state["first_headers"],
            json={"password": "wrong-password"},
        )
        assert response.status_code == 401

    limited = client.post(
        "/api/admin/bootstrap/claim",
        headers=bootstrap_state["first_headers"],
        json={"password": "first-pass"},
    )
    assert limited.status_code == 429


def test_first_admin_claim_is_atomic_under_concurrency(tmp_path):
    manager = UserManager(tmp_path / "concurrent")
    first = manager.create_user("concurrent_first", "first-pass")
    second = manager.create_user("concurrent_second", "second-pass")
    barrier = threading.Barrier(2)
    results = []

    def claim(user_id: str, password: str):
        barrier.wait()
        try:
            results.append(manager.claim_first_system_admin(user_id, password))
        except ValueError as exc:
            results.append(str(exc))

    threads = [
        threading.Thread(target=claim, args=(first["user_id"], "first-pass")),
        threading.Thread(target=claim, args=(second["user_id"], "second-pass")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert manager.count_system_admins() == 1
    assert results.count(True) == 1
    assert sum("already exists" in str(result) for result in results) == 1


def test_administrator_can_manage_roles_with_password_reauthentication(bootstrap_state):
    client = bootstrap_state["client"]
    manager = bootstrap_state["manager"]
    first_id = bootstrap_state["first"]["user_id"]
    second_id = bootstrap_state["second"]["user_id"]
    manager.claim_first_system_admin(first_id, "first-pass")

    assert client.get("/api/admin/users").status_code == 401
    assert client.get(
        "/api/admin/users", headers=bootstrap_state["second_headers"]
    ).status_code == 403

    listing = client.get(
        "/api/admin/users", headers=bootstrap_state["first_headers"]
    )
    assert listing.status_code == 200
    assert listing.json()["admin_count"] == 1
    assert {user["user_id"] for user in listing.json()["users"]} == {first_id, second_id}

    wrong_password = client.post(
        f"/api/admin/users/{second_id}/role",
        headers=bootstrap_state["first_headers"],
        json={"role": "admin", "current_password": "wrong-password"},
    )
    assert wrong_password.status_code == 401
    assert manager.get_system_role(second_id) == "user"

    promoted = client.post(
        f"/api/admin/users/{second_id}/role",
        headers=bootstrap_state["first_headers"],
        json={"role": "admin", "current_password": "first-pass"},
    )
    assert promoted.status_code == 200
    assert manager.count_system_admins() == 2

    demoted = client.post(
        f"/api/admin/users/{first_id}/role",
        headers=bootstrap_state["first_headers"],
        json={"role": "user", "current_password": "first-pass"},
    )
    assert demoted.status_code == 200
    assert manager.get_system_role(first_id) == "user"

    last_admin = client.post(
        f"/api/admin/users/{second_id}/role",
        headers=bootstrap_state["second_headers"],
        json={"role": "user", "current_password": "second-pass"},
    )
    assert last_admin.status_code == 409
    assert manager.get_system_role(second_id) == "admin"

    audit_records = [
        json.loads(line)
        for line in bootstrap_state["audit_path"].read_text(encoding="utf-8").splitlines()
    ]
    assert any(record["action"] == "admin.role.update" for record in audit_records)
    assert "first-pass" not in json.dumps(audit_records)
    assert "second-pass" not in json.dumps(audit_records)
