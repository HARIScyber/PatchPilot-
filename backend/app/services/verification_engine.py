"""Repeated baseline/patch verification using structured per-test results."""
from __future__ import annotations

import ast
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from .patcher import Patcher, _protected_target_reason
from .repo_manager import RepoManager
from .test_runner import PytestResult, PytestRunner

logger = logging.getLogger("patchpilot.services.verification_engine")
DECISIVE_RUNS = 3


def evaluate_test_evidence(
    baseline_runs: list[PytestResult],
    patched_runs: list[PytestResult],
    reproducing_test_ids: list[str],
    target_file: str,
) -> tuple[str, str, list[str]]:
    """Return a conservative status, reason, and flaky IDs from repeated XML results."""
    if _protected_target_reason(target_file):
        return "NOT_VERIFIED", "PATCH_MODIFIES_TEST_OR_CONFIGURATION", []
    if not reproducing_test_ids:
        return "NOT_VERIFIED", "NO_REPRODUCING_TEST", []
    if len(baseline_runs) != DECISIVE_RUNS or len(patched_runs) != DECISIVE_RUNS:
        return "PARTIALLY_VERIFIED", "INSUFFICIENT_REPEATED_RUNS", []
    if any(not result.structured_report or result.test_results is None
           for result in baseline_runs + patched_runs):
        return "NOT_VERIFIED", "STRUCTURED_TEST_RESULTS_UNAVAILABLE", []

    baseline_maps = [result.test_results or {} for result in baseline_runs]
    patched_maps = [result.test_results or {} for result in patched_runs]
    all_ids = set().union(*(set(row) for row in baseline_maps + patched_maps))
    flaky: list[str] = []
    for test_id in all_ids:
        baseline_values = [row.get(test_id) for row in baseline_maps]
        patched_values = [row.get(test_id) for row in patched_maps]
        if (any(value is None for value in baseline_values + patched_values)
                or len(set(baseline_values)) != 1 or len(set(patched_values)) != 1):
            flaky.append(test_id)
    if flaky:
        return "PARTIALLY_VERIFIED", "FLAKY_OR_INCONSISTENT_TEST_RESULTS", sorted(flaky)

    for test_id in reproducing_test_ids:
        if any(row.get(test_id) != "failed" for row in baseline_maps):
            return "NOT_VERIFIED", "NO_REPRODUCING_TEST", []
        if any(row.get(test_id) != "passed" for row in patched_maps):
            return "TESTS_FAILED", "REPRODUCING_TEST_STILL_FAILS", []

    baseline_passed = {test_id for test_id, state in baseline_maps[0].items() if state == "passed"}
    regressions = sorted(test_id for test_id in baseline_passed
                         if any(row.get(test_id) != "passed" for row in patched_maps))
    if regressions:
        return "TESTS_FAILED", "PREVIOUSLY_PASSING_TESTS_REGRESSED", regressions
    return "VERIFIED_AGAINST_DEFINED_TESTS", "REPRODUCING_TESTS_PASS_STABLY", []


class VerificationEngine:
    """Orchestrates three baseline and three patched runs in disposable snapshots."""

    def __init__(self):
        self.repo_manager = RepoManager()
        self.patcher = Patcher()
        self.test_runner = PytestRunner()

    @staticmethod
    def _write_regression_test(snapshot: Path, code: Optional[str]) -> None:
        if not code:
            return
        test_path = snapshot / "tests" / "test_patchpilot_regression.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(code, encoding="utf-8")

    @staticmethod
    def _generated_test_names(code: Optional[str]) -> list[str]:
        if not code:
            return []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        return [node.name for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_")]

    def verify_patch(
        self,
        project_id: str,
        target_file: str,
        diff_content: str,
        regression_test_code: Optional[str] = None,
        test_command_target: str = "tests",
        reproducing_test_ids: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        workspace = self.repo_manager.get_workspace_dir(project_id)
        environment = "none"
        trust_level = "unverified"
        if not workspace.exists():
            return {"verification_status": "EXECUTION_UNAVAILABLE",
                    "details": "Workspace directory does not exist.",
                    "execution_environment": environment, "trust_level": trust_level}

        protected_reason = _protected_target_reason(target_file)
        if protected_reason:
            return {"verification_status": "NOT_VERIFIED", "reason": "PATCH_MODIFIES_TEST_OR_CONFIGURATION",
                    "details": protected_reason, "execution_environment": environment,
                    "trust_level": trust_level}

        baseline_runs: list[PytestResult] = []
        for _ in range(DECISIVE_RUNS):
            snapshot = self.test_runner.create_disposable_snapshot(workspace)
            try:
                self._write_regression_test(snapshot, regression_test_code)
                result = self.test_runner.execute_pytest(snapshot, test_target=test_command_target)
                baseline_runs.append(result)
            finally:
                self.test_runner.cleanup_snapshot(snapshot)
            if result.execution_unavailable:
                return {"verification_status": "EXECUTION_UNAVAILABLE",
                        "baseline": asdict(result), "baseline_runs": [asdict(result)],
                        "patched": None, "regression_test": None,
                        "details": "Restricted execution is unavailable; repository code was not run.",
                        "execution_environment": environment, "trust_level": trust_level}
            if result.is_timeout:
                return {"verification_status": "PARTIALLY_VERIFIED",
                        "reason": "BASELINE_TIMEOUT", "baseline_runs": [asdict(r) for r in baseline_runs],
                        "patched_runs": [], "execution_environment": environment, "trust_level": trust_level}

        reproduction_ids = list(reproducing_test_ids or [])
        if not reproduction_ids and regression_test_code:
            names = set(self._generated_test_names(regression_test_code))
            first_results = baseline_runs[0].test_results or {}
            reproduction_ids = [test_id for test_id in first_results
                                if test_id.rsplit("::", 1)[-1] in names]

        patched_runs: list[PytestResult] = []
        for _ in range(DECISIVE_RUNS):
            snapshot = self.test_runner.create_disposable_snapshot(workspace)
            try:
                try:
                    self.patcher.apply_patch_to_workspace(snapshot, diff_content, target_file)
                except Exception:
                    return {"verification_status": "NOT_VERIFIED",
                            "reason": "PATCH_FAILED_TO_APPLY", "details": "Patch did not apply cleanly.",
                            "baseline_runs": [asdict(r) for r in baseline_runs],
                            "patched_runs": [asdict(r) for r in patched_runs],
                            "execution_environment": environment, "trust_level": trust_level}
                self._write_regression_test(snapshot, regression_test_code)
                result = self.test_runner.execute_pytest(snapshot, test_target=test_command_target)
                patched_runs.append(result)
            finally:
                self.test_runner.cleanup_snapshot(snapshot)
            if result.execution_unavailable:
                return {"verification_status": "EXECUTION_UNAVAILABLE",
                        "reason": "PATCHED_RUNNER_UNAVAILABLE",
                        "baseline_runs": [asdict(r) for r in baseline_runs],
                        "patched_runs": [asdict(r) for r in patched_runs],
                        "execution_environment": environment, "trust_level": trust_level}
            if result.is_timeout:
                return {"verification_status": "PARTIALLY_VERIFIED",
                        "reason": "PATCHED_RUN_TIMEOUT",
                        "baseline_runs": [asdict(r) for r in baseline_runs],
                        "patched_runs": [asdict(r) for r in patched_runs],
                        "execution_environment": environment, "trust_level": trust_level}

        status, reason, affected_ids = evaluate_test_evidence(
            baseline_runs, patched_runs, reproduction_ids, target_file)
        return {
            "verification_status": status,
            "reason": reason,
            "reproducing_test_ids": reproduction_ids,
            "affected_test_ids": affected_ids,
            "baseline": asdict(baseline_runs[-1]),
            "patched": asdict(patched_runs[-1]),
            "regression_test": asdict(patched_runs[-1]) if regression_test_code else None,
            "baseline_runs": [asdict(result) for result in baseline_runs],
            "patched_runs": [asdict(result) for result in patched_runs],
            "execution_environment": environment,
            "trust_level": trust_level,
        }
