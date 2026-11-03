"""Automated test suite for Phase 5: Sandbox execution, verification engine, and bounded self-repair loop."""
import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import init_db
from app.security.sandbox import get_sanitized_env, run_sandboxed_command
from app.services.test_runner import TestRunner
from app.services.repair_loop import RepairLoopOrchestrator


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def test_environment_sanitization():
    """Verify that sensitive tokens and API keys are stripped from the sandbox environment."""
    os.environ["META_API_KEY"] = "secret_key_123"
    os.environ["DATABASE_URL"] = "postgresql://user:pass@host/db"
    os.environ["SAFE_VARIABLE"] = "safe_value"

    clean_env = get_sanitized_env()
    assert "META_API_KEY" not in clean_env
    assert "DATABASE_URL" not in clean_env
    assert clean_env.get("SAFE_VARIABLE") == "safe_value"


def test_sandbox_unavailable_fails_closed(tmp_path):
    """Repository code is never executed on the host without restricted isolation."""
    exit_code, stdout, stderr, duration = run_sandboxed_command(["pytest", "tests"], tmp_path)
    assert exit_code == -126
    assert "EXECUTION_UNAVAILABLE" in stderr


def test_disposable_snapshot_cleanup(tmp_path):
    """Verify that snapshots are cleaned up and original workspace is unchanged."""
    ws = tmp_path / "original_ws"
    ws.mkdir()
    (ws / "main.py").write_text("orig_val = 1", encoding="utf-8")

    runner = TestRunner()
    snap = runner.create_disposable_snapshot(ws)
    assert snap.exists()
    assert (snap / "main.py").exists()

    # Modify snapshot
    (snap / "main.py").write_text("modified_val = 2", encoding="utf-8")
    assert "modified_val" in (snap / "main.py").read_text(encoding="utf-8")
    # Original must still be untouched!
    assert "orig_val" in (ws / "main.py").read_text(encoding="utf-8")

    runner.cleanup_snapshot(snap)
    assert not snap.exists()


def test_verification_sample_bug_lifecycle(client):
    """Test full verification of the sample calculator bug."""
    # 1. Load sample project
    sample_resp = client.post("/api/projects/load-sample")
    assert sample_resp.status_code == 200
    proj_id = sample_resp.json()["id"]

    # 2. Generate plan
    plan_resp = client.post(f"/api/projects/{proj_id}/repair-plan", json={})
    assert plan_resp.status_code == 200
    plan_id = plan_resp.json()["id"]

    # 3. Generate patch
    patch_resp = client.post(f"/api/projects/{proj_id}/patches/generate", json={"plan_id": plan_id})
    assert patch_resp.status_code == 200
    patch_id = patch_resp.json()["id"]

    # 4. Verify patch
    verif_resp = client.post(f"/api/patches/{patch_id}/verify", json={})
    assert verif_resp.status_code == 200
    verif_data = verif_resp.json()
    assert "verification_status" in verif_data
    assert verif_data["verification_status"] == "EXECUTION_UNAVAILABLE"
    assert verif_data["baseline_passed"] is None

    # 5. Check verification history
    hist_resp = client.get(f"/api/patches/{patch_id}/verification-history")
    assert hist_resp.status_code == 200
    assert len(hist_resp.json()) >= 1


def test_sample_workflow_reports_unavailable_execution_honestly(client):
    """Exercise the sample from analysis through evidence without claiming tests ran."""
    project = client.post("/api/projects/load-sample").json()
    project_id = project["id"]

    analysis = client.post(f"/api/projects/{project_id}/analyze").json()
    assert analysis["status"] == "success"
    assert analysis["findings_count"] > 0
    finding_id = analysis["findings"][0]["id"]

    plan = client.post(f"/api/projects/{project_id}/repair-plan", json={"finding_id": finding_id}).json()
    patch = client.post(f"/api/projects/{project_id}/patches/generate", json={"plan_id": plan["id"]}).json()
    assert patch["validation_status"] == "valid"

    generated = client.post(f"/api/patches/{patch['id']}/generate-tests")
    assert generated.status_code == 200
    verification = client.post(f"/api/patches/{patch['id']}/verify", json={}).json()
    assert verification["verification_status"] == "EXECUTION_UNAVAILABLE"
    assert verification["baseline_exit_code"] is None
    assert verification["patched_exit_code"] is None

    loop = client.post(f"/api/patches/{patch['id']}/repair-loop", json={"max_attempts": 3}).json()
    assert loop["final_status"] == "EXECUTION_UNAVAILABLE"
    assert loop["attempts_made"] == 1

    report = client.get(f"/api/projects/{project_id}/report").json()
    assert report["verification_evidence"]["verification_status"] == "EXECUTION_UNAVAILABLE"
    assert "not persisted" in report["ai_provenance"]


@pytest.mark.asyncio
async def test_bounded_repair_loop_attempt_limit(monkeypatch):
    """A failing verifier consumes exactly the configured number of attempts."""
    orchestrator = RepairLoopOrchestrator()
    attempted = []

    class AlwaysFail:
        def verify_patch(self, **kwargs):
            attempted.append(kwargs["diff_content"])
            return {"verification_status": "TESTS_FAILED", "patched": {"stderr": "failure"}}

    async def refine(**kwargs):
        return kwargs["current_diff"] + f"\n# candidate {kwargs['attempt']}\n"

    orchestrator.verification_engine = AlwaysFail()
    monkeypatch.setattr(orchestrator, "_refine_patch_with_feedback", refine)
    result = await orchestrator.execute_repair_loop(
        project_id="project",
        target_file="core.py",
        bug_description="bug",
        initial_diff="diff 0",
        max_attempts=3,
    )
    assert result["attempts_made"] == 3
    assert len(attempted) == 3
