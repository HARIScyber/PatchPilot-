"""Subprocess execution sandbox with timeout enforcement and secret redaction."""
from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger("patchpilot.security.sandbox")

DEFAULT_TIMEOUT_SECONDS = 30
MAX_OUTPUT_CHARS = 50000


def get_sanitized_env() -> Dict[str, str]:
    """Return environment variables with sensitive tokens and keys stripped."""
    clean_env = os.environ.copy()
    redacted_keys = [
        "META_API_KEY",
        "API_KEY",
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "DATABASE_URL",
        "AWS_SECRET_ACCESS_KEY",
        "OPENAI_API_KEY",
    ]
    for key in list(clean_env.keys()):
        for pattern in redacted_keys:
            if pattern in key.upper():
                clean_env.pop(key, None)
                break
    return clean_env


def run_sandboxed_command(
    cmd: str | list[str],
    cwd: Path | str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    extra_env: Optional[Dict[str, str]] = None,
) -> Tuple[int, str, str, float]:
    """Execute a command within a restricted sandbox.

    Returns:
        (exit_code, stdout, stderr, duration_seconds)
    """
    # Disposable directories and a cleaned environment are not process isolation.
    # Until a restricted container backend exists, fail closed for repository code.
    return (-126, "", "EXECUTION_UNAVAILABLE: restricted container isolation is not implemented.", 0.0)

    cwd_path = Path(cwd).resolve()
    if not cwd_path.exists():
        return (-1, "", f"Working directory {cwd_path} does not exist", 0.0)

    env = get_sanitized_env()
    if extra_env:
        env.update(extra_env)

    # Add cwd to PYTHONPATH so python imports work inside the project
    pythonpath = str(cwd_path)
    if "PYTHONPATH" in env:
        pythonpath = f"{str(cwd_path)}{os.pathsep}{env['PYTHONPATH']}"
    env["PYTHONPATH"] = pythonpath

    start_time = time.time()
    try:
        if isinstance(cmd, str):
            return (-126, "", "EXECUTION_UNAVAILABLE: shell commands are disabled.", 0.0)

        process = subprocess.run(
            cmd,
            cwd=str(cwd_path),
            env=env,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = round(time.time() - start_time, 3)

        stdout = process.stdout[:MAX_OUTPUT_CHARS]
        stderr = process.stderr[:MAX_OUTPUT_CHARS]
        return (process.returncode, stdout, stderr, duration)

    except subprocess.TimeoutExpired as exc:
        duration = round(time.time() - start_time, 3)
        stdout = (exc.stdout or "")[:MAX_OUTPUT_CHARS]
        stderr = f"Command timed out after {timeout} seconds."
        return (-124, stdout, stderr, duration)

    except FileNotFoundError as exc:
        duration = round(time.time() - start_time, 3)
        return (-127, "", f"Executable not found: {exc}", duration)

    except Exception as exc:
        duration = round(time.time() - start_time, 3)
        return (-1, "", f"Execution error: {str(exc)}", duration)
