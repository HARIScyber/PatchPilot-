"""Static analysis engine using Python AST to detect defect patterns without code execution."""
from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("patchpilot.services.static_analyzer")


class ASTDefectVisitor(ast.NodeVisitor):
    """Inspects AST nodes for suspicious patterns, anti-patterns, and security risks."""

    def __init__(self, file_path: str, source_lines: List[str]):
        self.file_path = file_path
        self.source_lines = source_lines
        self.findings: List[Dict[str, Any]] = []

    def _get_snippet(self, lineno: Optional[int], context_lines: int = 2) -> Optional[str]:
        if not lineno or lineno < 1 or lineno > len(self.source_lines):
            return None
        start = max(1, lineno - context_lines)
        end = min(len(self.source_lines), lineno + context_lines)
        lines = []
        for i in range(start, end + 1):
            prefix = "-> " if i == lineno else "   "
            lines.append(f"{prefix}{i:4d}: {self.source_lines[i - 1]}")
        return "\n".join(lines)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # 1. Detect mutable default arguments (list, dict, set)
        # Match defaults to argument names
        pos_defaults_start = len(node.args.args) - len(node.args.defaults)
        for idx, default in enumerate(node.args.defaults):
            if default is not None and isinstance(default, (ast.List, ast.Dict, ast.Set)):
                arg_name = node.args.args[pos_defaults_start + idx].arg if (pos_defaults_start + idx) < len(node.args.args) else "arg"
                lineno = getattr(default, "lineno", node.lineno)
                self.findings.append({
                    "id": str(uuid4()),
                    "finding_type": "mutable_default",
                    "severity": "high",
                    "file_path": self.file_path,
                    "line_number": lineno,
                    "title": f"Dangerous mutable default argument '{arg_name}' in '{node.name}'",
                    "description": (
                        f"Function '{node.name}' parameter '{arg_name}' uses a mutable default argument ({type(default).__name__}). "
                        "Python default arguments are evaluated once at function definition time, "
                        "causing state to be shared across invocations."
                    ),
                    "code_snippet": self._get_snippet(lineno),
                    "confidence": 0.95,
                    "recommended_action": f"Replace mutable default for '{arg_name}' with None and initialize inside function body.",
                })

        # 2. Check for test functions without assertions
        if node.name.startswith("test_") and not any(isinstance(n, ast.Assert) for n in ast.walk(node)):
            self.findings.append({
                "id": str(uuid4()),
                "finding_type": "missing_tests",
                "severity": "medium",
                "file_path": self.file_path,
                "line_number": node.lineno,
                "title": f"Test '{node.name}' contains no assertions",
                "description": "Test function runs without asserting conditions; it may produce false-positive passes.",
                "code_snippet": self._get_snippet(node.lineno),
                "confidence": 0.85,
                "recommended_action": "Add explicit assert statements verifying expected behavior.",
            })

        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        # Detect bare except or except Exception: pass
        for handler in node.handlers:
            is_bare = handler.type is None
            is_broad = isinstance(handler.type, ast.Name) and handler.type.id in ("Exception", "BaseException")
            
            # Check if body is just `pass`
            is_silent = (
                len(handler.body) == 1
                and isinstance(handler.body[0], ast.Pass)
            )

            if (is_bare or is_broad) and is_silent:
                lineno = handler.lineno
                self.findings.append({
                    "id": str(uuid4()),
                    "finding_type": "suspicious_exception",
                    "severity": "high",
                    "file_path": self.file_path,
                    "line_number": lineno,
                    "title": "Silenced exception (swallowed error)",
                    "description": (
                        "Exception is caught and silently discarded with 'pass'. "
                        "This frequently conceals unexpected defects and root causes."
                    ),
                    "code_snippet": self._get_snippet(lineno),
                    "confidence": 0.9,
                    "recommended_action": "Log the error, handle specific exceptions, or re-raise with context.",
                })

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Detect potentially unsafe subprocess execution with shell=True
        func_name = ""
        if isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        elif isinstance(node.func, ast.Name):
            func_name = node.func.id

        if func_name in ("Popen", "run", "call", "check_call", "check_output", "system"):
            for keyword in node.keywords:
                if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                    self.findings.append({
                        "id": str(uuid4()),
                        "finding_type": "shell_injection_risk",
                        "severity": "critical",
                        "file_path": self.file_path,
                        "line_number": node.lineno,
                        "title": "Unsafe subprocess execution with shell=True",
                        "description": "Executing subprocess commands with shell=True risks command injection vulnerabilities.",
                        "code_snippet": self._get_snippet(node.lineno),
                        "confidence": 0.95,
                        "recommended_action": "Pass command arguments as a list with shell=False.",
                    })

        self.generic_visit(node)


def analyze_python_file(file_path: Path, relative_path: str) -> List[Dict[str, Any]]:
    """Analyze a single Python file using AST inspection."""
    findings: List[Dict[str, Any]] = []

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
            source_lines = source.splitlines()
    except Exception as exc:
        return [{
            "id": str(uuid4()),
            "finding_type": "read_error",
            "severity": "medium",
            "file_path": relative_path,
            "line_number": 1,
            "title": f"Unable to read file: {relative_path}",
            "description": str(exc),
            "code_snippet": None,
            "confidence": 1.0,
            "recommended_action": "Check file permissions and encoding.",
        }]

    # 1. Check for syntax errors
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        snippet = None
        if exc.lineno and 1 <= exc.lineno <= len(source_lines):
            line = source_lines[exc.lineno - 1]
            col = exc.offset or 1
            pointer = " " * (col - 1) + "^"
            snippet = f"{exc.lineno:4d}: {line}\n      {pointer}"

        findings.append({
            "id": str(uuid4()),
            "finding_type": "syntax_error",
            "severity": "critical",
            "file_path": relative_path,
            "line_number": exc.lineno,
            "title": f"Syntax error: {exc.msg}",
            "description": f"File contains invalid Python syntax: {exc.msg}",
            "code_snippet": snippet,
            "confidence": 1.0,
            "recommended_action": "Fix syntax error to allow parsing and execution.",
        })
        return findings

    # 2. Run AST visitor
    visitor = ASTDefectVisitor(relative_path, source_lines)
    visitor.visit(tree)
    findings.extend(visitor.findings)

    return findings


def analyze_repository(workspace_path: Path | str) -> List[Dict[str, Any]]:
    """Analyze all Python files in the workspace without executing code."""
    workspace = Path(workspace_path)
    all_findings: List[Dict[str, Any]] = []

    for root, dirs, files in os.walk(workspace):
        # Skip virtualenvs, git, cache
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "venv", ".venv")]

        for file_name in files:
            if file_name.endswith(".py"):
                full_path = Path(root) / file_name
                rel_path = full_path.relative_to(workspace).as_posix()
                findings = analyze_python_file(full_path, rel_path)
                all_findings.extend(findings)

    return all_findings
