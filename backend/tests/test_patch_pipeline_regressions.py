"""Regression tests for unified diff and evidence status correctness."""
from pathlib import Path

from app.services.patcher import Patcher
from app.services.test_runner import PytestResult, PytestRunner
from app.services.verification_engine import VerificationEngine


def test_diff_applies_when_hunk_line_numbers_are_stale(tmp_path: Path):
    source = tmp_path / "module.py"
    source.write_text("first = 1\nsecond = 2\n", encoding="utf-8")
    diff = (
        "--- a/module.py\n+++ b/module.py\n"
        "@@ -80,2 +80,2 @@\n first = 1\n-second = 2\n+second = 3\n"
    )

    ok, error, result = Patcher().parse_and_validate_diff(tmp_path, diff, "module.py")

    assert ok, error
    assert result == "first = 1\r\nsecond = 3\r\n"


def test_diff_preserves_crlf_and_does_not_strip_added_whitespace(tmp_path: Path):
    source = tmp_path / "module.py"
    source.write_bytes(b"value = 'old'\r\n")
    diff = (
        "--- a/module.py\n+++ b/module.py\n"
        "@@ -1 +1 @@\n-value = 'old'\n+value = 'new' \n"
    )

    ok, error, result = Patcher().parse_and_validate_diff(tmp_path, diff, "module.py")

    assert ok, error
    assert result.encode("utf-8") == b"value = 'new' \r\n"


def test_stale_diff_context_is_rejected(tmp_path: Path):
    (tmp_path / "module.py").write_text("value = 2\n", encoding="utf-8")
    diff = "--- a/module.py\n+++ b/module.py\n@@ -1 +1 @@\n-value = 1\n+value = 3\n"

    ok, error, _ = Patcher().parse_and_validate_diff(tmp_path, diff, "module.py")

    assert not ok
    assert "context does not match" in error


def test_runner_does_not_fabricate_test_counts(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "app.services.test_runner.run_sandboxed_command",
        lambda **kwargs: (-126, "", "EXECUTION_UNAVAILABLE", 0.0),
    )

    result = PytestRunner().execute_pytest(tmp_path)

    assert result.execution_unavailable
    assert result.total_tests is None
    assert result.passed_tests is None
    assert result.failed_tests is None


def test_passing_baseline_does_not_prove_patch_fixed_bug(monkeypatch, tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    class Runner:
        def create_disposable_snapshot(self, path):
            return workspace

        def cleanup_snapshot(self, path):
            pass

        def execute_pytest(self, path, test_target="tests"):
            return PytestResult(True, 0, "1 passed", "", 0.1)

    engine = VerificationEngine()
    monkeypatch.setattr(engine.repo_manager, "get_workspace_dir", lambda project_id: workspace)
    engine.test_runner = Runner()
    monkeypatch.setattr(engine.patcher, "apply_patch_to_workspace", lambda *args: None)

    result = engine.verify_patch("project", "module.py", "unused diff")

    assert result["verification_status"] == "NOT_VERIFIED"
