"""Automated test suite for Phase 4: Repair planning, patch validation, approval, and test generation."""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import init_db
from app.services.patcher import Patcher
from app.services.test_generator import TestGenerator
from app.services.repair_planner import RepairPlanner


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_repair_planner_structured_output():
    """Verify repair planner produces validated structured output."""
    planner = RepairPlanner()
    plan = await planner.generate_plan(
        project_id="test-proj",
        bug_description="Loop off by one boundary condition",
        stack_trace='File "core/calculator.py", line 42, in compute_cumulative_total',
    )
    assert plan.problem_summary
    assert plan.root_cause
    assert len(plan.candidate_files) > 0
    assert len(plan.proposed_changes) > 0


def test_patch_diff_validation_syntax_error(tmp_path):
    """Verify that a patch introducing a syntax error is rejected by AST validation."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def hello():\n    return 42\n", encoding="utf-8")

    # Malformed patch introducing syntax error
    diff = (
        "--- a/sample.py\n"
        "+++ b/sample.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def hello():\n"
        "-    return 42\n"
        "+    return def syntax error\n"
    )

    patcher = Patcher()
    is_valid, err_msg, _ = patcher.parse_and_validate_diff(tmp_path, diff, "sample.py")
    assert not is_valid
    assert "syntax error" in (err_msg or "").lower()


def test_patch_path_traversal_rejected(tmp_path):
    """Verify that patches attempting to target outside the workspace are rejected."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("x = 1\n", encoding="utf-8")

    diff = (
        "--- a/../../secret.py\n"
        "+++ b/../../secret.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-x = 1\n"
        "+x = 2\n"
    )

    patcher = Patcher()
    is_valid, err_msg, _ = patcher.parse_and_validate_diff(tmp_path, diff, "../../secret.py")
    assert not is_valid
    assert "traversal" in (err_msg or "").lower() or "escapes" in (err_msg or "").lower()


def test_patch_header_must_match_expected_target(tmp_path):
    (tmp_path / "sample.py").write_text("x = 1\n", encoding="utf-8")
    diff = "--- a/other.py\n+++ b/other.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    valid, message, _ = Patcher().parse_and_validate_diff(tmp_path, diff, "sample.py")
    assert not valid
    assert "does not match" in (message or "")


def test_patch_context_and_line_counts_are_checked(tmp_path):
    (tmp_path / "sample.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    patcher = Patcher()
    stale = "--- a/sample.py\n+++ b/sample.py\n@@ -1,2 +1,2 @@\n x = 1\n-y = old\n+y = 3\n"
    valid, message, _ = patcher.parse_and_validate_diff(tmp_path, stale, "sample.py")
    assert not valid
    assert "context does not match" in (message or "")

    malformed = "--- a/sample.py\n+++ b/sample.py\n@@ -1,2 +1,1 @@\n x = 1\n-y = 2\n+y = 3\n"
    valid, message, _ = patcher.parse_and_validate_diff(tmp_path, malformed, "sample.py")
    assert not valid
    assert "line counts" in (message or "")


def test_diff_without_hunks_is_not_valid(tmp_path):
    (tmp_path / "sample.py").write_text("x = 1\n", encoding="utf-8")
    diff = "--- a/sample.py\n+++ b/sample.py\n"
    valid, message, _ = Patcher().parse_and_validate_diff(tmp_path, diff, "sample.py")
    assert not valid
    assert "no unified diff hunks" in (message or "")


@pytest.mark.asyncio
async def test_test_generator_valid_python():
    """Verify that generated regression test code parses without syntax errors."""
    gen = TestGenerator()
    code = await gen.generate_regression_test(
        bug_description="Sum excludes last element",
        target_file="core/calculator.py",
        patch_diff="--- a/core/calculator.py\n+++ b/core/calculator.py\n@@ -1,1 +1,1 @@\n",
    )
    import ast
    # Must parse successfully
    tree = ast.parse(code)
    assert any(isinstance(node, ast.FunctionDef) and node.name.startswith("test_") for node in ast.walk(tree))


def test_phase4_api_workflow(client):
    """Test full Phase 4 API workflow: load sample -> plan -> generate patch -> approve."""
    # 1. Load sample
    sample_resp = client.post("/api/projects/load-sample")
    assert sample_resp.status_code == 200
    proj_id = sample_resp.json()["id"]

    # 2. Generate repair plan
    plan_resp = client.post(f"/api/projects/{proj_id}/repair-plan", json={})
    assert plan_resp.status_code == 200
    plan_data = plan_resp.json()
    assert "problem_summary" in plan_data
    plan_id = plan_data["id"]

    # 3. Generate patch
    patch_resp = client.post(f"/api/projects/{proj_id}/patches/generate", json={"plan_id": plan_id})
    assert patch_resp.status_code == 200
    patch_data = patch_resp.json()
    patch_id = patch_data["id"]
    assert "diff_content" in patch_data
    assert patch_data["validation_status"] == "valid"
    assert "@@" in patch_data["diff_content"]

    # 4. Attempt to apply without approval -> should fail 400
    apply_resp = client.post(f"/api/patches/{patch_id}/apply")
    assert apply_resp.status_code == 400
    assert "approved" in apply_resp.json()["detail"].lower()

    # 5. Approve patch
    approve_resp = client.post(f"/api/patches/{patch_id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["is_approved"] is True

    # 6. Generate regression test
    test_resp = client.post(f"/api/patches/{patch_id}/generate-tests")
    assert test_resp.status_code == 200
    assert "test_code" in test_resp.json()


def test_approved_patch_rejects_stale_target(client):
    from app.services.repo_manager import RepoManager

    project = client.post("/api/projects/load-sample").json()
    plan = client.post(f"/api/projects/{project['id']}/repair-plan", json={}).json()
    patch = client.post(
        f"/api/projects/{project['id']}/patches/generate",
        json={"plan_id": plan["id"]},
    ).json()
    assert patch["validation_status"] == "valid"
    assert client.post(f"/api/patches/{patch['id']}/approve").status_code == 200

    workspace = RepoManager().get_workspace_dir(project["id"])
    target = workspace / patch["target_file"]
    target.write_text(target.read_text(encoding="utf-8") + "# changed after review\n", encoding="utf-8")
    response = client.post(f"/api/patches/{patch['id']}/apply")
    assert response.status_code == 409
    assert "changed since patch generation" in response.json()["detail"]
