"""Bug localization service ranking relevant files and functions using multi-signal evidence."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("patchpilot.services.localization")


class BugLocalizer:
    """Ranks candidate files and functions based on stack traces, bug descriptions, and AST signals."""

    def __init__(self, workspace_path: Path | str):
        self.workspace_path = Path(workspace_path)

    def extract_stack_trace_locations(self, stack_trace: Optional[str]) -> List[Dict[str, Any]]:
        """Extract file and line references from standard Python tracebacks."""
        if not stack_trace:
            return []

        locations = []
        # Pattern matching: File "...", line 123, in func_name
        pattern = re.compile(r'File\s+["\']([^"\']+)["\'],\s+line\s+(\d+)(?:,\s+in\s+([a-zA-Z0-9_<>]+))?')
        for match in pattern.finditer(stack_trace):
            raw_path = match.group(1)
            line_no = int(match.group(2))
            func_name = match.group(3) or ""

            # Check if raw_path matches a file in workspace
            posix_path = raw_path.replace("\\", "/")
            matched_rel = None
            for p in self.workspace_path.rglob("*.py"):
                rel = p.relative_to(self.workspace_path).as_posix()
                if posix_path.endswith(rel) or rel.endswith(posix_path):
                    matched_rel = rel
                    break

            locations.append({
                "file_path": matched_rel or Path(raw_path).name,
                "line_number": line_no,
                "function_name": func_name,
                "source": "stack_trace",
                "weight": 1.0,
            })

        return locations

    def rank_candidates(
        self,
        bug_description: Optional[str] = None,
        stack_trace: Optional[str] = None,
        static_findings: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Compute ranked candidate defect locations across the project."""
        file_scores: Dict[str, float] = {}
        file_reasons: Dict[str, List[str]] = {}
        file_lines: Dict[str, List[int]] = {}

        # 1. Score from stack trace (highest precision signal)
        st_locs = self.extract_stack_trace_locations(stack_trace)
        for loc in st_locs:
            fp = loc["file_path"]
            file_scores[fp] = file_scores.get(fp, 0.0) + 0.8
            file_reasons.setdefault(fp, []).append(
                f"Referenced in stack trace at line {loc['line_number']} (in {loc['function_name']})"
            )
            file_lines.setdefault(fp, []).append(loc["line_number"])

        # 2. Score from static analysis findings
        for f in (static_findings or []):
            fp = f["file_path"]
            sev = f.get("severity", "medium")
            weight = {"critical": 0.6, "high": 0.4, "medium": 0.2, "low": 0.1, "info": 0.05}.get(sev, 0.2)
            file_scores[fp] = file_scores.get(fp, 0.0) + weight
            file_reasons.setdefault(fp, []).append(f"Static analysis finding: {f.get('title')}")
            if f.get("line_number"):
                file_lines.setdefault(fp, []).append(f["line_number"])

        # 3. Score from keyword overlap with bug description
        desc_tokens = set(re.findall(r"[a-zA-Z_]{3,}", (bug_description or "").lower()))
        for py_file in self.workspace_path.rglob("*.py"):
            rel = py_file.relative_to(self.workspace_path).as_posix()
            if any(part.startswith(".") or part in ("node_modules", "venv", ".venv") for part in py_file.parts):
                continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="replace").lower()
                matches = [tok for tok in desc_tokens if tok in content]
                if matches:
                    overlap_score = min(0.4, len(matches) * 0.05)
                    file_scores[rel] = file_scores.get(rel, 0.0) + overlap_score
                    file_reasons.setdefault(rel, []).append(
                        f"Matched {len(matches)} query terms ({', '.join(matches[:4])})"
                    )
            except Exception:
                pass

        # Format and sort candidates
        ranked: List[Dict[str, Any]] = []
        for file_path, score in sorted(file_scores.items(), key=lambda x: x[1], reverse=True):
            is_test_file = any(part.lower() in {"test", "tests"} for part in Path(file_path).parts) or Path(file_path).name.lower().startswith("test_")
            if is_test_file:
                score *= 0.25
                file_reasons.setdefault(file_path, []).append("Test files are downranked; inspect the implementation called by the test.")
            primary_line = file_lines.get(file_path, [None])[0] if file_lines.get(file_path) else None
            confidence = min(0.98, max(0.2, score))

            ranked.append({
                "id": str(uuid4()),
                "finding_type": "bug_localization_candidate",
                "severity": "high" if confidence > 0.6 else "medium",
                "file_path": file_path,
                "line_number": primary_line,
                "title": f"Candidate bug location: {file_path}",
                "description": "; ".join(file_reasons.get(file_path, [])),
                "confidence": round(confidence, 2),
                "recommended_action": "Inspect target file around identified lines for defect reproduction.",
                "is_confirmed": False,
            })

        return ranked
