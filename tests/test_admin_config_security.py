from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import app.auth as auth
import app.setup_api as setup_api
from config.settings import AppConfig, FeatureConfig
from core.user_manager import UserManager


@pytest.fixture()
def users(tmp_path):
    manager = UserManager(tmp_path / "data")
    regular = manager.create_user("regular", "regular-pass")
    admin = manager.create_user("administrator", "admin-pass")
    manager.set_system_role(admin["user_id"], "admin")
    return {
        "manager": manager,
        "regular": regular,
        "admin": admin,
        "regular_token": manager.generate_token(regular["user_id"]),
        "admin_token": manager.generate_token(admin["user_id"]),
    }


@pytest.fixture()
def config_state():
    return AppConfig(
        llm=FeatureConfig(
            provider="openai",
            api_key="secret-llm",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
        ),
        llm_fallback=FeatureConfig(
            provider="openai",
            api_key="secret-fallback",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
        ),
        vlm=FeatureConfig(
            provider="openai",
            api_key="secret-vlm",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
        ),
        embedding=FeatureConfig(
            provider="openai",
            api_key="secret-embedding",
            base_url="https://api.openai.com/v1",
            model="text-embedding-3-large",
        ),
        mineru=FeatureConfig(provider="mineru", api_key="secret-mineru"),
        openalex=FeatureConfig(
            provider="openalex",
            api_key="secret-openalex",
            base_url="https://api.openalex.org",
        ),
    )


@pytest.fixture()
def client(monkeypatch, users, config_state, tmp_path):
    monkeypatch.setattr(auth, "get_user_manager", lambda: users["manager"])
    monkeypatch.setattr(setup_api, "get_full_config", lambda: config_state)
    monkeypatch.setattr(
        setup_api,
        "check_all_features",
        lambda: {"llm": True, "vlm": True, "embedding": True, "mineru": True, "openalex": True},
    )
    monkeypatch.setattr(setup_api, "AUDIT_LOG_PATH", tmp_path / "admin_audit.jsonl")
    monkeypatch.delenv("LEARNANYTHING_ALLOW_PRIVATE_API_ENDPOINTS", raising=False)

    api = FastAPI()
    api.include_router(setup_api.router)
    return TestClient(api)


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_system_roles_require_password_and_protect_last_admin(tmp_path):
    manager = UserManager(tmp_path / "roles")
    with pytest.raises(ValueError, match="password-authenticated"):
        manager.set_system_role("default", "admin")

    first = manager.create_user("first", "first-pass")
    second = manager.create_user("second", "second-pass")
    manager.set_system_role(first["user_id"], "admin")
    with pytest.raises(ValueError, match="last system administrator"):
        manager.set_system_role(first["user_id"], "user")

    manager.set_system_role(second["user_id"], "admin")
    assert manager.set_system_role(first["user_id"], "user") is True
    assert manager.get_system_role(first["user_id"]) == "user"


def test_invalid_bearer_never_falls_back_to_local_user(monkeypatch, users):
    monkeypatch.setattr(auth, "get_user_manager", lambda: users["manager"])
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user_id("default", "Bearer invalid")
    assert exc.value.status_code == 401


def test_config_requires_system_administrator(client, users):
    assert client.get("/api/setup/config").status_code == 401
    assert client.get(
        "/api/setup/config", headers=_bearer(users["regular_token"])
    ).status_code == 403
    response = client.get(
        "/api/setup/config", headers=_bearer(users["admin_token"])
    )
    assert response.status_code == 200
    payload_text = response.text
    assert "secret-" not in payload_text
    assert response.json()["llm"]["configured"] is True
    assert response.json()["openalex"]["configured"] is True
    assert "api_key" not in response.json()["llm"]
    assert "api_key" not in response.json()["openalex"]


def test_public_setup_status_does_not_expose_filesystem_path(client):
    response = client.get("/api/setup/status")
    assert response.status_code == 200
    assert "config_path" not in response.json()


def test_raw_config_endpoint_is_removed(client, users):
    response = client.get(
        "/api/setup/config-raw", headers=_bearer(users["admin_token"])
    )
    assert response.status_code == 404


def test_partial_update_keeps_existing_secret_and_audits_safely(
    client, users, config_state, monkeypatch, tmp_path
):
    captured = {}

    def capture_update(config):
        captured["config"] = config

    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(setup_api, "update_config", capture_update)
    monkeypatch.setattr(setup_api, "AUDIT_LOG_PATH", audit_path)

    response = client.post(
        "/api/setup/config",
        headers=_bearer(users["admin_token"]),
        json={"llm": {"model": "gpt-4o-mini", "api_key": ""}},
    )
    assert response.status_code == 200
    assert captured["config"].llm.api_key == "secret-llm"
    assert captured["config"].llm.model == "gpt-4o-mini"
    assert "secret-" not in audit_path.read_text(encoding="utf-8")


def test_connection_test_rejects_private_target_before_network(client, users):
    response = client.post(
        "/api/setup/test/llm",
        headers=_bearer(users["admin_token"]),
        json={
            "provider": "custom",
            "api_key": "temporary-secret",
            "base_url": "http://127.0.0.1:9999/v1",
            "model": "test-model",
        },
    )
    assert response.status_code == 400
    assert "HTTPS" in response.json()["detail"] or "Private" in response.json()["detail"]


def test_provider_change_requires_a_new_secret(client, users):
    response = client.post(
        "/api/setup/config",
        headers=_bearer(users["admin_token"]),
        json={
            "llm": {
                "provider": "custom",
                "api_key": "",
                "base_url": "https://example.com/v1",
                "model": "custom-model",
            }
        },
    )
    assert response.status_code == 400
    assert "new API Key" in response.json()["detail"]


def test_openalex_update_keeps_existing_secret(client, users, config_state, monkeypatch):
    captured = {}
    monkeypatch.setattr(setup_api, "update_config", lambda config: captured.setdefault("config", config))

    response = client.post(
        "/api/setup/config",
        headers=_bearer(users["admin_token"]),
        json={"openalex": {"provider": "openalex", "api_key": "", "enabled": True}},
    )

    assert response.status_code == 200
    assert captured["config"].openalex.api_key == "secret-openalex"
    assert "secret-openalex" not in response.text
