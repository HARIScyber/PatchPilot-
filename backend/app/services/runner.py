"""Runner interface supporting docker, browser_wasm, and none execution backends."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from ..core.config import get_settings

logger = logging.getLogger("patchpilot.services.runner")

PYODIDE_VERSION = "0.26.4"


@dataclass
class StructuredTestResult:
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
    test_results: Optional[Dict[str, str]] = None
    structured_report: bool = False
    trust_level: str = "unverified"
    execution_backend: str = "none"


class BaseRunner(ABC):
    """Abstract test suite execution runner."""

    @abstractmethod
    def execute(
        self,
        snapshot_path: Path,
        test_selector: str = "tests",
        timeout_seconds: int = 25,
    ) -> StructuredTestResult:
        """Run tests within the snapshot and return structured results."""
        pass


class NoneRunner(BaseRunner):
    """Fails closed; returns EXECUTION_UNAVAILABLE without running code."""

    def execute(
        self,
        snapshot_path: Path,
        test_selector: str = "tests",
        timeout_seconds: int = 25,
    ) -> StructuredTestResult:
        return StructuredTestResult(
            passed=None,
            exit_code=None,
            stdout="",
            stderr="EXECUTION_UNAVAILABLE: restricted container isolation is not implemented.",
            duration_seconds=0.0,
            execution_unavailable=True,
            structured_report=False,
            trust_level="unverified",
            execution_backend="none",
        )


class DockerRunner(BaseRunner):
    """Runs tests inside an ephemeral, locked-down Docker container with strict constraints."""

    IMAGE_NAME = "patchpilot-sandbox-runner:latest"

    def validate_selector(self, snapshot_path: Path, selector: str) -> str:
        """Validate test selector against command injection and directory traversal."""
        cleaned = selector.strip()
        if not cleaned:
            return "tests"
        if cleaned.startswith("-"):
            raise ValueError(f"Test selector may not start with leading '-': {selector}")

        # Check for path traversal escaping the snapshot
        target = (snapshot_path / cleaned).resolve()
        try:
            target.relative_to(snapshot_path.resolve())
        except ValueError as exc:
            raise ValueError(f"Test selector escapes snapshot workspace: {selector}") from exc

        # Disallow dangerous shell metacharacters
        if re.search(r"[;&|`$><]", cleaned):
            raise ValueError(f"Test selector contains invalid characters: {selector}")

        return cleaned

    def execute(
        self,
        snapshot_path: Path,
        test_selector: str = "tests",
        timeout_seconds: int = 25,
    ) -> StructuredTestResult:
        validated_target = self.validate_selector(snapshot_path, test_selector)
        report_file = snapshot_path / ".patchpilot-junit.xml"
        if report_file.exists():
            report_file.unlink()

        container_name = f"patchpilot-run-{uuid4().hex[:12]}"
        snapshot_posix = str(snapshot_path.resolve()).replace("\\", "/")

        docker_cmd = [
            "docker", "run",
            "--name", container_name,
            "--rm",
            "--network", "none",
            "--user", "10001:10001",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "100",
            "--memory", "512m",
            "--cpus", "1.0",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "-v", f"{snapshot_posix}:/workspace:rw",
            "-w", "/workspace",
            self.IMAGE_NAME,
            "pytest", validated_target, "-v", "--tb=short",
            "--junitxml=/workspace/.patchpilot-junit.xml",
        ]

        start_time = time.time()
        is_timeout = False
        try:
            proc = subprocess.Popen(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout_seconds)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                is_timeout = True
                # Timeout enforcement by explicitly killing the container
                subprocess.run(["docker", "kill", container_name], capture_output=True)
                stdout, stderr = proc.communicate()
                exit_code = -124
        except FileNotFoundError:
            return StructuredTestResult(
                passed=None,
                exit_code=None,
                stdout="",
                stderr="EXECUTION_UNAVAILABLE: docker daemon is not accessible.",
                duration_seconds=0.0,
                execution_unavailable=True,
                structured_report=False,
                trust_level="unverified",
                execution_backend="docker",
            )

        duration = round(time.time() - start_time, 3)
        return self._parse_structured_xml(report_file, exit_code, stdout, stderr, duration, is_timeout)

    @staticmethod
    def _parse_structured_xml(
        report_path: Path,
        exit_code: int,
        stdout: str,
        stderr: str,
        duration: float,
        is_timeout: bool,
    ) -> StructuredTestResult:
        total = passed_count = failed_count = None
        test_results: Dict[str, str] = {}
        structured_report = False

        if report_path.is_file():
            try:
                root = ET.parse(report_path).getroot()
                structured_report = True
                suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
                total = sum(int(s.attrib.get("tests", 0)) for s in suites)
                failed_count = sum(int(s.attrib.get("failures", 0)) + int(s.attrib.get("errors", 0)) for s in suites)
                skipped = sum(int(s.attrib.get("skipped", 0)) for s in suites)
                passed_count = max(0, total - failed_count - skipped)

                for case in root.iter("testcase"):
                    classname = case.attrib.get("classname", "")
                    name = case.attrib.get("name", "")
                    if not name:
                        continue
                    test_id = f"{classname}::{name}" if classname else name
                    if case.find("failure") is not None or case.find("error") is not None:
                        test_results[test_id] = "failed"
                    elif case.find("skipped") is not None:
                        test_results[test_id] = "skipped"
                    else:
                        test_results[test_id] = "passed"
            except (OSError, ET.ParseError, ValueError):
                structured_report = False

        passed = (exit_code == 0) if structured_report else False

        return StructuredTestResult(
            passed=passed if not is_timeout else False,
            exit_code=exit_code,
            stdout=stdout[:50000],
            stderr=stderr[:50000],
            duration_seconds=duration,
            total_tests=total,
            passed_tests=passed_count,
            failed_tests=failed_count,
            is_timeout=is_timeout,
            execution_unavailable=False,
            test_results=test_results if structured_report else None,
            structured_report=structured_report,
            trust_level="verified_docker",
            execution_backend="docker",
        )


class BrowserWasmRunner(BaseRunner):
    """Manages signed run tokens and parses structured results produced by Pyodide in Web Worker."""

    def __init__(self, signing_secret: Optional[str] = None):
        self.signing_secret = signing_secret or get_settings().SESSION_SIGNING_SECRET.get_secret_value() or "wasm-default-secret-32-chars-long"

    def generate_signed_run_token(
        self,
        project_id: str,
        patch_id: str,
        expires_in_seconds: int = 600,
    ) -> str:
        """Create a tamper-proof HMAC-SHA256 signed run token."""
        expires_at = int(time.time()) + expires_in_seconds
        payload = {"project_id": project_id, "patch_id": patch_id, "exp": expires_at, "nonce": uuid4().hex}
        raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        signature = hmac.new(self.signing_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
        encoded = base64.urlsafe_b64encode(raw_bytes).decode("utf-8").rstrip("=")
        return f"{encoded}.{signature}"

    def verify_run_token(self, token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Verify the signature and expiration of a run token."""
        try:
            parts = token.split(".")
            if len(parts) != 2:
                return False, None
            encoded, sig = parts
            padded = encoded + "=" * (-len(encoded) % 4)
            raw_bytes = base64.urlsafe_b64decode(padded.encode("utf-8"))
            expected_sig = hmac.new(self.signing_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                return False, None
            payload = json.loads(raw_bytes.decode("utf-8"))
            if payload.get("exp", 0) < int(time.time()):
                return False, None
            return True, payload
        except Exception:
            return False, None

    def execute(
        self,
        snapshot_path: Path,
        test_selector: str = "tests",
        timeout_seconds: int = 25,
    ) -> StructuredTestResult:
        """Server-side stub for WASM runner: instructs client to execute in worker."""
        return StructuredTestResult(
            passed=None,
            exit_code=None,
            stdout="",
            stderr="CLIENT_EXECUTION_REQUIRED: execute in browser Pyodide Web Worker using signed token.",
            duration_seconds=0.0,
            execution_unavailable=False,
            structured_report=False,
            trust_level="client_reported",
            execution_backend="browser_wasm",
        )

    def parse_client_report(self, report_payload: Dict[str, Any]) -> StructuredTestResult:
        """Validate and parse structured JSON results submitted from browser Pyodide."""
        passed = bool(report_payload.get("passed"))
        total = int(report_payload.get("total_tests", 0))
        passed_cnt = int(report_payload.get("passed_tests", 0))
        failed_cnt = int(report_payload.get("failed_tests", 0))
        duration = float(report_payload.get("duration_seconds", 0.0))
        test_results = report_payload.get("test_results") or {}

        return StructuredTestResult(
            passed=passed,
            exit_code=0 if passed else 1,
            stdout=str(report_payload.get("stdout", ""))[:50000],
            stderr=str(report_payload.get("stderr", ""))[:50000],
            duration_seconds=duration,
            total_tests=total,
            passed_tests=passed_cnt,
            failed_tests=failed_cnt,
            is_timeout=bool(report_payload.get("is_timeout", False)),
            execution_unavailable=False,
            test_results=test_results,
            structured_report=True,
            trust_level="client_reported",
            execution_backend="browser_wasm",
        )


def get_runner(backend_name: Optional[str] = None) -> BaseRunner:
    """Factory returning the configured runner instance."""
    backend = (backend_name or get_settings().EXECUTION_BACKEND).strip().lower()
    if backend == "docker":
        return DockerRunner()
    elif backend in ("browser_wasm", "wasm"):
        return BrowserWasmRunner()
    return NoneRunner()
