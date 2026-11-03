"""Patch service for unified diff generation, validation, dry-run, and application."""
from __future__ import annotations

import ast
import hashlib
import logging
import re
import difflib
from pathlib import Path
from typing import Optional, Tuple

from .meta_client import MetaClient
from .repo_manager import RepoManager

logger = logging.getLogger("patchpilot.services.patcher")


class PatchValidationError(Exception):
    """Raised when a candidate patch is invalid, malformed, or unsafe."""
    pass


def _protected_target_reason(relative_path: str) -> Optional[str]:
    normalized = Path(relative_path).as_posix()
    parts = Path(normalized).parts
    filename = Path(normalized).name.lower()
    if any(part.lower() in {"test", "tests"} for part in parts) or filename.startswith("test_"):
        return "Edits to existing test files are disallowed."
    if (normalized.startswith((".github/", ".gitlab/", ".circleci/")) or filename in {
            "pyproject.toml", "pytest.ini", "tox.ini", "requirements.txt",
            "package.json", "package-lock.json", "dockerfile", "config.py", "settings.py"}
            or Path(normalized).suffix.lower() in {".yml", ".yaml", ".toml", ".ini"}):
        return "Edits to configuration or CI files are disallowed."
    return None


class Patcher:
    """Manages patch generation, unified diff parsing, AST verification, and application."""

    def __init__(self):
        self.meta_client = MetaClient()
        self.repo_manager = RepoManager()

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Calculate SHA-256 hash of a file."""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha.update(chunk)
        return sha.hexdigest()

    def build_diffs_from_edit_blocks(self, workspace: Path, edits: list[dict]) -> dict[str, str]:
        """Validate exact-match edits in memory and render diffs without touching source files."""
        root = workspace.resolve()
        if not edits or len(edits) > 5:
            raise PatchValidationError("Edit set must contain between 1 and 5 files.")
        results: dict[str, str] = {}
        total_changes = 0
        for edit in edits:
            relative = edit.get("path")
            old_text, new_text = edit.get("old_text"), edit.get("new_text")
            if not all(isinstance(x, str) for x in (relative, old_text, new_text)) or not relative:
                raise PatchValidationError("Each edit needs string path, old_text, and new_text fields.")
            target = self.resolve_target_file(root, relative)
            if not target.is_file():
                raise PatchValidationError(f"Edit target does not exist: {relative}")
            rel = target.relative_to(root).as_posix()
            protected_reason = _protected_target_reason(rel)
            if protected_reason:
                raise PatchValidationError(f"{protected_reason} Target: {rel}")
            original_bytes = target.read_bytes()
            encoding = "utf-8-sig" if original_bytes.startswith(b"\xef\xbb\xbf") else "utf-8"
            try:
                original = original_bytes.decode(encoding)
            except UnicodeDecodeError as exc:
                raise PatchValidationError(f"Edit target is not valid UTF-8: {rel}") from exc
            if original.count(old_text) != 1:
                raise PatchValidationError(f"old_text must match exactly once in {rel}; found {original.count(old_text)} matches.")
            updated = original.replace(old_text, new_text, 1)
            total_changes += len(old_text.splitlines()) + len(new_text.splitlines())
            if total_changes > 300:
                raise PatchValidationError("Edit set exceeds 300 changed lines.")
            if rel.endswith(".py"):
                try:
                    before, after = ast.parse(original), ast.parse(updated)
                except SyntaxError as exc:
                    raise PatchValidationError(f"Edit produces invalid Python in {rel}: {exc.msg}") from exc
                if sum(isinstance(n, ast.Assert) for n in ast.walk(after)) < sum(isinstance(n, ast.Assert) for n in ast.walk(before)):
                    raise PatchValidationError("Edits may not remove assertions.")
                old_imports = self._python_imports(before)
                new_imports = self._python_imports(after)
                blocked = {"subprocess", "socket", "requests", "httpx", "urllib"}
                if (new_imports - old_imports) & blocked:
                    raise PatchValidationError("Edits may not add subprocess or network imports.")
                if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                       and isinstance(n.func.value, ast.Name) and n.func.value.id == "os"
                       and n.func.attr == "system" for n in ast.walk(after)) and not any(
                           isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                           and isinstance(n.func.value, ast.Name) and n.func.value.id == "os"
                           and n.func.attr == "system" for n in ast.walk(before)):
                    raise PatchValidationError("Edits may not add os.system calls.")
                if re.search(r"\bif\s+(?:input|value|arg|argument)\s*==\s*(['\"]).*?\1", new_text):
                    raise PatchValidationError("Literal-specific input special-casing is disallowed.")
            diff = difflib.unified_diff(
                original.splitlines(keepends=True), updated.splitlines(keepends=True),
                fromfile=f"a/{rel}", tofile=f"b/{rel}", lineterm="\n")
            results[rel] = "".join(diff)
        return results

    @staticmethod
    def _python_imports(tree: ast.AST) -> set[str]:
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        return imports

    @classmethod
    def _validate_python_change(cls, original: str, updated: str, relative_path: str) -> None:
        before = ast.parse(original, filename=relative_path)
        after = ast.parse(updated, filename=relative_path)
        if sum(isinstance(node, ast.Assert) for node in ast.walk(after)) < sum(
                isinstance(node, ast.Assert) for node in ast.walk(before)):
            raise PatchValidationError("Patch may not remove existing Python assertions.")
        forbidden = {"subprocess", "socket", "requests", "httpx", "urllib",
                     "multiprocessing", "pty", "ftplib", "telnetlib"}
        if (cls._python_imports(after) - cls._python_imports(before)) & forbidden:
            raise PatchValidationError("Patch introduces a process or network import.")
        def system_calls(tree: ast.AST) -> int:
            return sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                       and isinstance(node.func.value, ast.Name) and node.func.value.id == "os"
                       and node.func.attr == "system" for node in ast.walk(tree))
        if system_calls(after) > system_calls(before):
            raise PatchValidationError("Patch may not introduce os.system calls.")
        pattern = re.compile(r"\bif\s+(?:input|value|arg|argument)\s*==\s*(['\"]).*?\1")
        if pattern.search(updated) and not pattern.search(original):
            raise PatchValidationError("Literal-specific input special-casing is disallowed.")

    @staticmethod
    def resolve_target_file(workspace: Path, relative_path: str) -> Path:
        """Resolve a repository path and ensure it remains inside the workspace."""
        workspace_root = workspace.resolve()
        rel = Path(relative_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise PatchValidationError("Target file path escapes project workspace.")
        target = (workspace_root / rel).resolve()
        try:
            target.relative_to(workspace_root)
        except ValueError as exc:
            raise PatchValidationError("Target file escapes project workspace.") from exc
        return target

    async def generate_patch(
        self,
        project_id: str,
        target_file_rel: str,
        problem_summary: str,
        root_cause: str,
        proposed_changes: list[str],
    ) -> str:
        """Prompt the selected provider to generate a unified diff for the defect."""
        protected_reason = _protected_target_reason(target_file_rel)
        if protected_reason:
            raise PatchValidationError(protected_reason)
        workspace = self.repo_manager.get_workspace_dir(project_id)
        target_file = self.resolve_target_file(workspace, target_file_rel)
        if not target_file.exists():
            raise PatchValidationError(f"Target file '{target_file_rel}' does not exist.")

        try:
            raw_bytes = target_file.read_bytes()
            encoding = "utf-8-sig" if raw_bytes.startswith(b"\xef\xbb\xbf") else "utf-8"
            file_content = raw_bytes.decode(encoding)
        except UnicodeDecodeError as exc:
            raise PatchValidationError("Target file is not valid UTF-8; refusing lossy patching.") from exc

        system_prompt = (
            "You are PatchPilot, an autonomous software repair engineer. Generate a clean, unified diff "
            "that fixes the described defect without modifying unrelated code. "
            "Format your output strictly as a unified diff starting with '--- a/...' and '+++ b/...'. "
            "Do not output markdown code blocks unless necessary. Do not include extra conversational text."
        )

        user_content = (
            f"Problem Summary:\n{problem_summary}\n\n"
            f"Root Cause:\n{root_cause}\n\n"
            f"Proposed Changes:\n{chr(10).join(proposed_changes)}\n\n"
            f"File: {target_file_rel}\n"
            f"Current Content:\n```python\n{file_content}\n```"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        resp = await self.meta_client.chat_completion(messages, temperature=0.1)
        raw_diff = resp["choices"][0]["message"]["content"]

        # Extract diff block if wrapped in markdown
        diff_match = re.search(r"```(?:diff)?\s*([\s\S]*?)```", raw_diff)
        if diff_match:
            diff_content = diff_match.group(1)
        else:
            diff_content = raw_diff

        # Ensure minimal unified diff header if missing
        if not diff_content.startswith("---"):
            diff_content = f"--- a/{target_file_rel}\n+++ b/{target_file_rel}\n{diff_content}"

        return diff_content

    def parse_and_validate_diff(
        self,
        workspace: Path,
        diff_content: str,
        expected_target_file: str,
    ) -> Tuple[bool, Optional[str], str]:
        """Validate that the diff is safe, targets an existing file, and applies cleanly.

        Returns: (is_valid, error_message, patched_code)
        """
        headers = [line for line in diff_content.splitlines() if line.startswith(("--- ", "+++ "))]
        expected_path = Path(expected_target_file).as_posix()
        protected_reason = _protected_target_reason(expected_path)
        if protected_reason:
            return False, protected_reason, ""
        old_headers = [line[4:].split("\t", 1)[0].strip() for line in headers if line.startswith("--- ")]
        new_headers = [line[4:].split("\t", 1)[0].strip() for line in headers if line.startswith("+++ ")]
        if len(old_headers) != 1 or len(new_headers) != 1:
            return False, "Diff must contain exactly one old and one new file header.", ""
        for header_path, prefix in ((old_headers[0], "a/"), (new_headers[0], "b/")):
            normalized = header_path.replace("\\", "/")
            if normalized.startswith("/") or ".." in normalized.split("/") or not normalized.startswith(prefix):
                return False, f"Unsafe diff target path (absolute path or traversal): {header_path}", ""
            if normalized[len(prefix):] != expected_path:
                return False, f"Diff target does not match expected file '{expected_path}'.", ""

        try:
            target_file = self.resolve_target_file(workspace, expected_target_file)
        except PatchValidationError as exc:
            return False, str(exc), ""
        if not target_file.exists():
            return False, f"Target file '{expected_target_file}' not found.", ""

        raw_bytes = target_file.read_bytes()
        encoding = "utf-8-sig" if raw_bytes.startswith(b"\xef\xbb\xbf") else "utf-8"
        try:
            original_text = raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            return False, "Target file is not valid UTF-8; refusing lossy patching.", ""
        original_lines = original_text.splitlines(keepends=True)

        # Apply diff hunks in a temporary copy
        try:
            patched_lines = self._apply_unified_diff(original_lines, diff_content)
            patched_code = "".join(patched_lines)

            # Check Python AST syntax of patched code
            if expected_target_file.endswith(".py"):
                self._validate_python_change(original_text, patched_code, expected_target_file)

            return True, None, patched_code

        except SyntaxError as syn_err:
            return False, f"Patch introduces syntax error at line {syn_err.lineno}: {syn_err.msg}", ""
        except Exception as exc:
            return False, f"Diff application failed: {str(exc)}", ""

    def _apply_unified_diff(self, original_lines: list[str], diff_text: str) -> list[str]:
        """Simple, robust unified diff hunk application."""
        lines = diff_text.splitlines()
        hunks = []
        current_hunk = None

        hunk_header_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)$")

        for line in lines:
            m = hunk_header_re.match(line)
            if m:
                if current_hunk:
                    hunks.append(current_hunk)
                orig_start = int(m.group(1))
                orig_count = int(m.group(2)) if m.group(2) else 1
                new_start = int(m.group(3))
                new_count = int(m.group(4)) if m.group(4) else 1
                current_hunk = {
                    "orig_start": orig_start,
                    "orig_count": orig_count,
                    "new_start": new_start,
                    "new_count": new_count,
                    "lines": [],
                }
            elif current_hunk:
                if line.startswith("\\"):
                    raise ValueError("No-newline diff markers are unsupported.")
                if line.startswith(("+", "-", " ")):
                    current_hunk["lines"].append(line)
                else:
                    raise ValueError("Malformed unified diff hunk line.")

        if current_hunk:
            hunks.append(current_hunk)

        if not hunks:
            raise ValueError("Diff contains no unified diff hunks.")

        result_lines: list[str] = []
        cursor = 0
        newline = "\r\n" if any(line.endswith("\r\n") for line in original_lines) else "\n"
        for hunk in hunks:
            old_start = hunk["orig_start"]
            old_count = hunk["orig_count"]
            new_start = hunk["new_start"]
            new_count = hunk["new_count"]
            old_lines = [ln[1:] for ln in hunk["lines"] if ln.startswith((" ", "-"))]
            if old_count != len(old_lines):
                raise ValueError("Diff hunk line counts do not match its header.")
            if old_lines:
                candidates = range(cursor, max(cursor, len(original_lines) - len(old_lines) + 1))
                orig_idx = next((idx for idx in candidates if all(
                    original_lines[idx + off].rstrip("\r\n") == expected
                    for off, expected in enumerate(old_lines))), None)
                if orig_idx is None:
                    raise ValueError("Diff context does not match the current file; patch is stale or malformed.")
            else:
                # Insertion-only hunks have no old context; use the hunk position as a bounded hint.
                orig_idx = min(len(original_lines), max(cursor, old_start - 1))
            result_lines.extend(original_lines[cursor:orig_idx])
            consumed = 0
            produced = 0
            for hline in hunk["lines"]:
                prefix, content = hline[0], hline[1:]
                if prefix in (" ", "-"):
                    source_idx = orig_idx + consumed
                    if source_idx >= len(original_lines) or original_lines[source_idx].rstrip("\r\n") != content:
                        raise ValueError("Diff context does not match the current file; patch is stale or malformed.")
                    if prefix == " ":
                        result_lines.append(original_lines[source_idx])
                        produced += 1
                    consumed += 1
                else:
                    result_lines.append(content + newline)
                    produced += 1
            if consumed != old_count or produced != new_count:
                raise ValueError("Diff hunk line counts do not match its header.")
            cursor = orig_idx + consumed
        result_lines.extend(original_lines[cursor:])
        return result_lines

    def apply_patch_to_workspace(
        self,
        workspace: Path,
        diff_content: str,
        target_file_rel: str,
    ) -> None:
        """Explicitly apply validated patch directly to the project workspace."""
        is_valid, err, patched_code = self.parse_and_validate_diff(workspace, diff_content, target_file_rel)
        if not is_valid:
            raise PatchValidationError(f"Cannot apply invalid patch: {err}")

        target_file = self.resolve_target_file(workspace, target_file_rel)
        raw_bytes = target_file.read_bytes()
        encoding = "utf-8-sig" if raw_bytes.startswith(b"\xef\xbb\xbf") else "utf-8"
        target_file.write_bytes(patched_code.encode(encoding))
        logger.info("Successfully applied patch to %s", target_file)
