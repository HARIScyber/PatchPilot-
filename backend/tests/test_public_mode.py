from fastapi.testclient import TestClient
import pytest

from app.core import config
from app.core.config import Settings
from app.main import app
from app.security import sandbox
from app.services.meta_client import MetaAPIError, MetaClient


@pytest.fixture
def public_settings(monkeypatch):
    monkeypatch.setattr(config, "_settings", Settings(
        APP_MODE="public_demo", DEMO_MODE=False, MODEL_API_KEY="",
        ENABLE_UPLOAD=False, EXECUTION_BACKEND="none", PUBLIC_DEMO_ENABLED=False,
        PUBLIC_DAILY_META_CALL_CAP=1, PUBLIC_MAX_ATTEMPTS=2,
        PUBLIC_MAX_TOKENS_PER_CALL=2048,
        ALLOWED_ORIGINS="https://patchpilot.pages.dev",
    ))


def test_public_demo_rejects_upload_before_processing_body(public_settings):
    with TestClient(app) as client:
        response = client.post("/api/projects/not-a-project/upload", files={"file": ("repo.zip", b"not-a-zip")})
    assert response.status_code == 403
    assert response.json()["error_code"] == "UPLOAD_DISABLED"


def test_public_demo_rejects_custom_project_creation(public_settings):
    with TestClient(app) as client:
        response = client.post("/api/projects/", json={"name": "custom"})
    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "PUBLIC_SAMPLE_ONLY"


def test_public_kill_switch_blocks_meta_without_a_provider_call(public_settings):
    client = MetaClient()
    with pytest.raises(MetaAPIError) as exc:
        import asyncio
        asyncio.run(client.chat_completion([{"role": "user", "content": "hello"}]))
    assert exc.value.provider_status == "PUBLIC_DEMO_DISABLED"


def test_public_sandbox_never_spawns_a_process(public_settings, monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("public demo must never spawn subprocesses")
    monkeypatch.setattr(sandbox.subprocess, "run", forbidden)
    result = sandbox.run_sandboxed_command(["python", "-c", "raise SystemExit(1)"], tmp_path)
    assert result[0] == -126
    assert "EXECUTION_UNAVAILABLE" in result[2]


def test_public_config_has_no_credentials_and_reports_execution_mode(public_settings):
    with TestClient(app) as client:
        response = client.get("/api/public/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "public_demo"
    assert payload["execution_backend"] == "none"
    assert payload["daily_meta_call_cap"] == 1
    assert "MODEL_API_KEY" not in response.text


def test_launch_readiness_fails_closed_and_disables_public_ai(public_settings):
    config.get_settings().PUBLIC_AI_ENABLED = True
    with TestClient(app) as client:
        response = client.get("/api/public/readiness")
        action = client.post("/api/providers/meta/test")
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "blocked"
    assert payload["public_ai_enabled"] is False
    assert {gate["id"] for gate in payload["gates"]} == {f"G{i}" for i in range(1, 9)}
    assert all(gate["status"] == "fail" for gate in payload["gates"] if gate["id"] != "G8")
    assert next(gate for gate in payload["gates"] if gate["id"] == "G8")["status"] == "pass"
    assert action.status_code == 503
    assert action.json()["error_code"] == "PUBLIC_DEMO_DISABLED"


def test_public_stats_returns_only_database_aggregate_counts(public_settings):
    with TestClient(app) as client:
        response = client.get("/api/public/stats")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"projects", "runs", "verified_runs"}
    assert all(isinstance(value, int) and value >= 0 for value in payload.values())


def test_public_daily_call_counter_enforces_cap(public_settings):
    client = MetaClient()
    with TestClient(app):
        client._reserve_public_call()
        with pytest.raises(MetaAPIError) as exc:
            client._reserve_public_call()
    assert exc.value.provider_status == "PUBLIC_DAILY_CAP_EXHAUSTED"


def test_public_cors_does_not_allow_untrusted_origin(public_settings):
    with TestClient(app) as client:
        response = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_production_cors_allows_exact_frontend_origin_without_credentials():
    with TestClient(app) as client:
        response = client.options("/api/health", headers={
            "Origin": "https://patchpilot-delta.vercel.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://patchpilot-delta.vercel.app"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert response.headers.get("access-control-allow-credentials") != "true"


def test_health_routes_do_not_expose_internal_database_details():
    with TestClient(app) as client:
        health = client.get("/api/health")
        database = client.get("/api/health/database")
        ready = client.get("/api/health/ready")
    assert health.status_code == 200
    assert "version" in health.json()
    assert "sqlite" not in health.text.lower()
    assert "database" not in health.json()
    assert database.status_code in {200, 503}
    assert "detail" not in database.json()
    assert ready.status_code in {200, 503}
    assert "EXECUTION_UNAVAILABLE" == ready.json()["execution_status"]


def test_basic_health_does_not_touch_database_or_provider(monkeypatch):
    from app import main

    def forbidden(*args, **kwargs):
        raise AssertionError("basic health must not access dependencies")

    monkeypatch.setattr(main, "check_db_health", forbidden)
    monkeypatch.setattr(main, "get_cached_meta_status", forbidden)
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_deep_health_checks_database_but_does_not_expose_database_details():
    with TestClient(app) as client:
        response = client.get("/api/health/deep")
    assert response.status_code in {200, 503}
    assert response.json()["database"] in {"ok", "unavailable"}
    assert "sqlite" not in response.text.lower()
