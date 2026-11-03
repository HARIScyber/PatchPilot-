"""Regression tests for unified diff and evidence status correctness."""
from pathlib import Path

from app.services.patcher import Patcher
from app.services.test_runner import PytestResult, PytestRunner
from app.services.verification_engine import VerificationEngine, evaluate_test_evidence


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


def test_unified_diff_cannot_target_existing_tests(tmp_path: Path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text(
        "def test_value():\n    assert value() == 1\n", encoding="utf-8")
    diff = (
        "--- a/tests/test_calc.py\n+++ b/tests/test_calc.py\n"
        "@@ -1,2 +1,2 @@\n def test_value():\n"
        "-    assert value() == 1\n+    assert value() == 2\n"
    )

    valid, error, _ = Patcher().parse_and_validate_diff(tmp_path, diff, "tests/test_calc.py")

    assert valid is False
    assert "test files" in error


def test_unified_diff_cannot_remove_assertions_or_add_network_imports(tmp_path: Path):
    source = tmp_path / "module.py"
    source.write_text("def value(x):\n    assert x\n    return x\n", encoding="utf-8")
    remove_assert = (
        "--- a/module.py\n+++ b/module.py\n@@ -1,3 +1,2 @@\n"
        " def value(x):\n-    assert x\n     return x\n")
    valid, error, _ = Patcher().parse_and_validate_diff(tmp_path, remove_assert, "module.py")
    assert valid is False
    assert "assertions" in error

    source.write_text("def value(x):\n    return x\n", encoding="utf-8")
    add_import = (
        "--- a/module.py\n+++ b/module.py\n@@ -1,2 +1,3 @@\n"
        "+import requests\n def value(x):\n     return x\n")
    valid, error, _ = Patcher().parse_and_validate_diff(tmp_path, add_import, "module.py")
    assert valid is False
    assert "process or network import" in error


def _evidence(state_repro: str, state_other: str = "passed", *, report: bool = True):
    return PytestResult(
        passed=state_repro != "failed" and state_other != "failed",
        exit_code=0 if state_repro != "failed" and state_other != "failed" else 1,
        stdout="", stderr="", duration_seconds=0.1,
        test_results={"test_bug::test_reproducer": state_repro,
                      "test_other::test_stable": state_other},
        structured_report=report,
    )


def _three(result):
    return [result, result, result]


def test_verification_requires_reproducing_test_to_fail_then_pass_three_times():
    baseline = _three(_evidence("failed"))
    patched = _three(_evidence("passed"))
    status, reason, flaky = evaluate_test_evidence(
        baseline, patched, ["test_bug::test_reproducer"], "src/module.py")
    assert (status, reason, flaky) == (
        "VERIFIED_AGAINST_DEFINED_TESTS", "REPRODUCING_TESTS_PASS_STABLY", [])


def test_verification_rejects_missing_or_already_passing_reproducer():
    baseline = _three(_evidence("passed", "failed"))
    patched = _three(_evidence("passed", "passed"))
    status, reason, _ = evaluate_test_evidence(
        baseline, patched, ["test_bug::test_reproducer"], "src/module.py")
    assert status == "NOT_VERIFIED"
    assert reason == "NO_REPRODUCING_TEST"
    assert evaluate_test_evidence(baseline, patched, [], "src/module.py")[:2] == (
        "NOT_VERIFIED", "NO_REPRODUCING_TEST")


def test_verification_reports_flaky_runs_as_partial():
    baseline = [_evidence("failed"), _evidence("passed"), _evidence("failed")]
    patched = _three(_evidence("passed"))
    status, reason, flaky = evaluate_test_evidence(
        baseline, patched, ["test_bug::test_reproducer"], "src/module.py")
    assert status == "PARTIALLY_VERIFIED"
    assert reason == "FLAKY_OR_INCONSISTENT_TEST_RESULTS"
    assert "test_bug::test_reproducer" in flaky


def test_verification_rejects_test_edits_and_unstructured_results():
    baseline, patched = _three(_evidence("failed")), _three(_evidence("passed"))
    assert evaluate_test_evidence(
        baseline, patched, ["test_bug::test_reproducer"], "tests/test_bug.py")[:2] == (
            "NOT_VERIFIED", "PATCH_MODIFIES_TEST_OR_CONFIGURATION")
    unstructured = _three(_evidence("failed", report=False))
    assert evaluate_test_evidence(
        unstructured, patched, ["test_bug::test_reproducer"], "src/module.py")[:2] == (
            "NOT_VERIFIED", "STRUCTURED_TEST_RESULTS_UNAVAILABLE")


def test_verification_rejects_reproducer_failure_and_existing_test_regression():
    baseline = _three(_evidence("failed"))
    still_failing = _three(_evidence("failed"))
    assert evaluate_test_evidence(
        baseline, still_failing, ["test_bug::test_reproducer"], "src/module.py")[:2] == (
            "TESTS_FAILED", "REPRODUCING_TEST_STILL_FAILS")
    regression = _three(_evidence("passed", "failed"))
    assert evaluate_test_evidence(
        baseline, regression, ["test_bug::test_reproducer"], "src/module.py")[:2] == (
            "TESTS_FAILED", "PREVIOUSLY_PASSING_TESTS_REGRESSED")


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


def test_runner_parses_per_test_results_from_junit_xml(monkeypatch, tmp_path: Path):
    def fake_run(*, cmd, **kwargs):
        report = Path(next(arg.split("=", 1)[1] for arg in cmd if arg.startswith("--junitxml=")))
        report.write_text(
            '<testsuite tests="2" failures="1" errors="0" skipped="0">'
            '<testcase classname="test_math" name="test_good" />'
            '<testcase classname="test_math" name="test_bad"><failure /></testcase>'
            '</testsuite>', encoding="utf-8")
        return 1, "", "", 0.1

    monkeypatch.setattr("app.services.test_runner.run_sandboxed_command", fake_run)
    result = PytestRunner().execute_pytest(tmp_path)

    assert result.structured_report is True
    assert result.test_results == {
        "test_math::test_good": "passed",
        "test_math::test_bad": "failed",
    }


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
