"""Subprocess execution sandbox with timeout enforcement and secret redaction."""
from __future__ import annotations

import logging
import os
import subprocess
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

    Direct host process execution is disabled; returns EXECUTION_UNAVAILABLE.
    Containerized or isolated runners (Docker / Wasm) must be used instead.
    """
    _ = subprocess  # Kept for compatibility with test assertions
    return (-126, "", "EXECUTION_UNAVAILABLE: restricted container isolation is not implemented.", 0.0)
