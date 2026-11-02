"""Isolated test execution runner using disposable snapshots, sanitized environments, and timeout enforcement."""
from __future__ import annotations

import logging
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..security.sandbox import run_sandboxed_command

logger = logging.getLogger("patchpilot.services.test_runner")


@dataclass
class PytestResult:
    passed: Optional[bool]
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_seconds: float
    total_tests: Optional[int] = None
    passed_tests: Optional[int] = None
    failed_tests: Optional[int] = None
    is_timeout: bool = False
    execution_unavailable: bool = False
    details: Optional[Dict[str, Any]] = None


class PytestRunner:
    """Executes test suites inside disposable snapshots without mutating original workspace."""

    def __init__(self):
        # Locate system python for running pytest
        import sys
        self.python_bin = sys.executable

    def create_disposable_snapshot(self, workspace_path: Path) -> Path:
        """Create a full isolated temporary copy of the workspace."""
        temp_dir = Path(tempfile.mkdtemp(prefix="patchpilot_sandbox_"))
        # Copy workspace files
        for item in workspace_path.iterdir():
            if item.name in (".git", "__pycache__", ".pytest_cache", "workspaces", ".venv"):
                continue
            dest = temp_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, ignore=shutil.ignore_patterns("*.pyc", "__pycache__"))
            else:
                shutil.copy2(item, dest)
        return temp_dir

    def cleanup_snapshot(self, snapshot_path: Path) -> None:
        """Safely remove the temporary snapshot directory."""
        if snapshot_path.exists() and "patchpilot_sandbox_" in str(snapshot_path):
            shutil.rmtree(snapshot_path, ignore_errors=True)

    def execute_pytest(
        self,
        snapshot_path: Path,
        test_target: str = "tests",
        timeout_seconds: int = 25,
    ) -> PytestResult:
        """Run pytest within the snapshot and parse test summary."""
        report_path = snapshot_path / ".patchpilot-junit.xml"
        cmd = [self.python_bin, "-m", "pytest", test_target, "-v", "--tb=short",
               f"--junitxml={report_path}"]

        exit_code, stdout, stderr, duration = run_sandboxed_command(
            cmd=cmd,
            cwd=snapshot_path,
            timeout=timeout_seconds,
        )

        is_timeout = (exit_code == -124)
        passed = None if exit_code == -126 else (exit_code == 0)

        # Parse only pytest's machine-readable report; never infer counts from human output.
        total = passed_count = failed_count = None
        try:
            root = ET.parse(report_path).getroot()
            suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
            total = sum(int(suite.attrib.get("tests", 0)) for suite in suites)
            failed_count = sum(int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0)) for suite in suites)
            skipped = sum(int(suite.attrib.get("skipped", 0)) for suite in suites)
            passed_count = max(0, total - failed_count - skipped)
        except (OSError, ET.ParseError, ValueError):
            pass

        return PytestResult(
            passed=passed,
            exit_code=None if exit_code == -126 else exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            total_tests=total,
            passed_tests=passed_count,
            failed_tests=failed_count,
            is_timeout=is_timeout,
            execution_unavailable=(exit_code == -126),
        )


# Backward-compatible names for API/tests; prevent pytest treating imported classes as tests.
TestExecutionResult = PytestResult
TestExecutionResult.__test__ = False
TestRunner = PytestRunner
TestRunner.__test__ = False
