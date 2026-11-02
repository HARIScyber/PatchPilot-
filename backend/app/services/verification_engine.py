"""Verification engine comparing baseline and patched execution evidence in isolated environments."""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, Optional

from .patcher import Patcher
from .repo_manager import RepoManager
from .test_runner import PytestResult, PytestRunner

logger = logging.getLogger("patchpilot.services.verification_engine")


class VerificationEngine:
    """Orchestrates differential test execution and determines verified statuses."""

    def __init__(self):
        self.repo_manager = RepoManager()
        self.patcher = Patcher()
        self.test_runner = PytestRunner()

    def verify_patch(
        self,
        project_id: str,
        target_file: str,
        diff_content: str,
        regression_test_code: Optional[str] = None,
        test_command_target: str = "tests",
    ) -> Dict[str, Any]:
        """Execute baseline and patched test runs in disposable snapshots."""
        workspace = self.repo_manager.get_workspace_dir(project_id)
        if not workspace.exists():
            return {
                "verification_status": "EXECUTION_UNAVAILABLE",
                "details": "Workspace directory does not exist on server.",
            }

        # 1. Baseline Test Run
        baseline_snap = self.test_runner.create_disposable_snapshot(workspace)
        try:
            baseline_res = self.test_runner.execute_pytest(baseline_snap, test_target=test_command_target)
        finally:
            self.test_runner.cleanup_snapshot(baseline_snap)

        if baseline_res.execution_unavailable:
            return {"verification_status": "EXECUTION_UNAVAILABLE", "baseline": asdict(baseline_res), "patched": None, "regression_test": None,
                    "details": "Restricted container isolation is unavailable; repository code was not executed."}

        # 2. Patched Test Run
        patched_snap = self.test_runner.create_disposable_snapshot(workspace)
        patched_res: Optional[PytestResult] = None
        regression_res: Optional[PytestResult] = None
        patch_applied_ok = False

        try:
            # Apply patch inside disposable snapshot
            try:
                self.patcher.apply_patch_to_workspace(patched_snap, diff_content, target_file)
                patch_applied_ok = True
            except Exception as apply_err:
                return {
                    "verification_status": "NOT_VERIFIED",
                    "baseline": asdict(baseline_res),
                    "patched": None,
                    "regression_test": None,
                    "error": f"Failed to apply patch to sandbox snapshot: {str(apply_err)}",
                }

            # Run existing test suite on patched snapshot
            patched_res = self.test_runner.execute_pytest(patched_snap, test_target=test_command_target)

            # If regression test was provided, write and execute it
            if regression_test_code:
                reg_file = patched_snap / "tests" / "test_patchpilot_regression.py"
                reg_file.parent.mkdir(parents=True, exist_ok=True)
                reg_file.write_text(regression_test_code, encoding="utf-8")
                regression_res = self.test_runner.execute_pytest(
                    patched_snap,
                    test_target="tests/test_patchpilot_regression.py",
                )

        finally:
            self.test_runner.cleanup_snapshot(patched_snap)

        # 3. Determine Verification Status
        # Truth-based verification logic:
        # A patch is verified if:
        # - Patched tests passed (exit_code 0)
        # - Regression tests (if any) passed (exit_code 0)
        # - And baseline was either failing or verified clean
        if patched_res is None or patched_res.execution_unavailable or patched_res.is_timeout:
            status = "EXECUTION_UNAVAILABLE"
        elif patched_res.passed and (regression_res is None or regression_res.passed):
            # A passing baseline cannot show that the candidate fixes the reported defect.
            status = "VERIFIED_AGAINST_DEFINED_TESTS" if baseline_res.passed is False else "NOT_VERIFIED"
        elif not patched_res.passed and baseline_res.passed:
            status = "TESTS_FAILED"  # New regression introduced!
        elif not patched_res.passed:
            status = "TESTS_FAILED"
        elif regression_res and not regression_res.passed:
            status = "PARTIALLY_VERIFIED"
        else:
            status = "REQUIRES_HUMAN_REVIEW"

        return {
            "verification_status": status,
            "patch_applied_cleanly": patch_applied_ok,
            "baseline": asdict(baseline_res),
            "patched": asdict(patched_res) if patched_res else None,
            "regression_test": asdict(regression_res) if regression_res else None,
        }
