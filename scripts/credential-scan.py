"""Scan tracked and unignored workspace files for common credential formats."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path


PATTERNS = {
    "Meta model key": re.compile(r"\bLLM_[A-Za-z0-9_-]{24,}"),
    "Google Gemini API key": re.compile(r"\b(?:AIza[0-9A-Za-z_-]{30,}|AQ\.[A-Za-z0-9_-]{24,})"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
MAX_FILE_BYTES = 5 * 1024 * 1024


def main() -> int:
    try:
        git = shutil.which("git")
        if not git and sys.platform == "win32":
            windows_git = Path(r"C:\Program Files\Git\cmd\git.exe")
            if windows_git.is_file():
                git = str(windows_git)
        if not git:
            raise FileNotFoundError("git executable not found")
        paths = subprocess.check_output(
            [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            stderr=subprocess.PIPE,
        ).split(b"\0")
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Credential scan could not enumerate repository files: {type(exc).__name__}", file=sys.stderr)
        return 2

    findings: list[tuple[str, str]] = []
    for raw_path in paths:
        if not raw_path:
            continue
        path = Path(raw_path.decode("utf-8", errors="surrogateescape"))
        try:
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                continue
            content = path.read_bytes().decode("utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                findings.append((path.as_posix(), label))

    if findings:
        for path, label in findings:
            print(f"POSSIBLE CREDENTIAL: {path} [{label}]")
        print("Credential scan failed. Values were suppressed.", file=sys.stderr)
        return 1
    # Also inspect reachable Git history; never print the matched secret text.
    try:
        history = subprocess.check_output(
            [git, "log", "--all", "-p", "--format=", "--", "."],
            stderr=subprocess.PIPE,
        ).decode("utf-8", errors="ignore")
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Credential scan could not inspect Git history: {type(exc).__name__}", file=sys.stderr)
        return 2
    for label, pattern in PATTERNS.items():
        if pattern.search(history):
            print(f"POSSIBLE CREDENTIAL IN GIT HISTORY [{label}]")
            print("Revoke the credential and clean repository history before publishing.", file=sys.stderr)
            return 1
    print("Credential scan passed: no configured credential patterns found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
