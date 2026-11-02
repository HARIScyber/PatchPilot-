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
