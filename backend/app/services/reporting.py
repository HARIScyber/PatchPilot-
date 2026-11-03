"""Evidence reporting service generating auditable verification reports and audit trails."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from sqlalchemy.orm import Session

from ..models.audit_event import AuditEvent
from ..models.finding import Finding
from ..models.generated_test import GeneratedTest
from ..models.patch import Patch
from ..models.project import Project
from ..models.repair_plan import RepairPlan
from ..models.verification_run import VerificationRun

logger = logging.getLogger("patchpilot.services.reporting")


class EvidenceReporter:
    """Builds auditable evidence reports separating model hypotheses from physical execution results."""

    def generate_project_report(self, db: Session, project_id: str) -> Dict[str, Any]:
        """Aggregate all evidence for a project into a structured report."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return {"error": "Project not found"}

        findings = db.query(Finding).filter(Finding.project_id == project_id).all()
        plans = db.query(RepairPlan).filter(RepairPlan.project_id == project_id).order_by(RepairPlan.created_at.desc()).all()
        patches = db.query(Patch).filter(Patch.project_id == project_id).order_by(Patch.created_at.desc()).all()
        tests = db.query(GeneratedTest).filter(GeneratedTest.project_id == project_id).order_by(GeneratedTest.created_at.desc()).all()
        runs = db.query(VerificationRun).filter(VerificationRun.project_id == project_id).order_by(VerificationRun.created_at.desc()).all()
        events = db.query(AuditEvent).filter(AuditEvent.project_id == project_id).order_by(AuditEvent.created_at.asc()).all()

        latest_run = runs[0] if runs else None
        latest_patch = (next((p for p in patches if p.id == latest_run.patch_id), None)
                        if latest_run else (patches[0] if patches else None))
        latest_plan = plans[0] if plans else None
        verification_details = {}
        if latest_run and latest_run.details:
            try:
                parsed = json.loads(latest_run.details)
                if isinstance(parsed, dict):
                    verification_details = parsed
            except (TypeError, ValueError):
                logger.warning("Verification details for run %s are not valid JSON.", latest_run.id)

        # Build clean audit timeline
        timeline = [
            {
                "timestamp": e.created_at.isoformat() if e.created_at else "",
                "event_type": e.event_type,
                "title": e.title,
            }
            for e in events
        ]

        report = {
            "meta": {
                "report_id": str(uuid4()),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "agent": "PatchPilot v0.1.0",
                "ai_provider": "Recorded per provider call; legacy records may not identify the provider",
                "model_id": None,
            },
            "project": {
                "id": project.id,
                "name": project.name,
                "language": project.language,
                "bug_description": project.bug_description,
                "stack_trace": project.stack_trace,
                "file_count": project.file_count,
                "size_bytes": project.size_bytes,
            },
            "investigation": {
                "findings_count": len(findings),
                "findings": [
                    {
                        "type": f.finding_type,
                        "severity": f.severity,
                        "file_path": f.file_path,
                        "line": f.line_number,
                        "title": f.title,
                        "description": f.description,
                        "confidence": f.confidence,
                    }
                    for f in findings
                ],
            },
            "ai_hypothesis": {
                "problem_summary": latest_plan.problem_summary if latest_plan else None,
                "root_cause": latest_plan.root_cause if latest_plan else None,
                "proposed_changes": json.loads(latest_plan.proposed_changes) if latest_plan else [],
                "expected_behavior": latest_plan.expected_behavior if latest_plan else None,
            },
            "patch_details": {
                "patch_id": latest_patch.id if latest_patch else None,
                "target_file": latest_patch.target_file if latest_patch else None,
                "diff_content": latest_patch.diff_content if latest_patch else None,
                "validation_status": latest_patch.validation_status if latest_patch else None,
                "is_approved": latest_patch.is_approved if latest_patch else False,
                "is_applied": latest_patch.is_applied if latest_patch else False,
            },
            "ai_provenance": "Provider-call provenance is not persisted on plan, patch, or test records; provider usage cannot be verified from this report.",
            "regression_testing": {
                "tests_generated": len(tests),
                "test_suites": [
                    {
                        "file": t.test_file_path,
                        "framework": t.test_framework,
                        "purpose": t.test_purpose,
                        "code": t.test_code,
                    }
                    for t in tests
                ],
            },
            "verification_evidence": {
                "verification_run_id": latest_run.id if latest_run else None,
                "patch_id": latest_run.patch_id if latest_run else None,
                "verification_status": latest_run.verification_status if latest_run else "NOT_VERIFIED",
                "reason": verification_details.get("reason"),
                "execution_environment": verification_details.get("execution_environment", "unknown"),
                "trust_level": verification_details.get("trust_level", "unverified"),
                "reproducing_test_ids": verification_details.get("reproducing_test_ids", []),
                "affected_test_ids": verification_details.get("affected_test_ids", []),
                "baseline_execution": {
                    "passed": latest_run.baseline_passed if latest_run else None,
                    "exit_code": latest_run.baseline_exit_code if latest_run else None,
                    "stdout_excerpt": (latest_run.baseline_stdout or "")[:1500] if latest_run else "",
                },
                "patched_execution": {
                    "passed": latest_run.patched_passed if latest_run else None,
                    "exit_code": latest_run.patched_exit_code if latest_run else None,
                    "stdout_excerpt": (latest_run.patched_stdout or "")[:1500] if latest_run else "",
                    "stderr_excerpt": (latest_run.patched_stderr or "")[:1500] if latest_run else "",
                    "duration_seconds": latest_run.duration_seconds if latest_run else 0.0,
                },
            },
            "timeline": timeline,
        }

        return report

    def render_markdown(self, report: Dict[str, Any]) -> str:
        """Render report dictionary as a GitHub Flavored Markdown document."""
        p = report.get("project", {})
        hyp = report.get("ai_hypothesis", {})
        patch = report.get("patch_details", {})
        verif = report.get("verification_evidence", {})

        def fenced(value: Any, language: str = "") -> list[str]:
            content = str(value or "")
            longest = max((len(m.group(0)) for m in re.finditer(r"`+", content)), default=2)
            marker = "`" * max(3, longest + 1)
            return [f"{marker}{language}", content, marker]

        md = [
            f"# PatchPilot Verification Report — {p.get('name', 'Project')}",
            f"**Report ID**: `{report.get('meta', {}).get('report_id')}` | **Generated**: {report.get('meta', {}).get('generated_at')}",
            f"**AI Provider**: {report.get('meta', {}).get('ai_provider')} | **Status**: `{verif.get('verification_status')}`",
            "",
            "## 1. Defect Description",
            f"> {p.get('bug_description', 'N/A')}",
            "",
        ]

        if p.get("stack_trace"):
            md.extend(["### Observed Stack Trace", *fenced(p.get("stack_trace"), "python"), ""])

        md.extend([
            "## 2. Root Cause Hypothesis",
            f"**Summary**: {hyp.get('problem_summary', 'N/A')}",
            f"**Root Cause**: {hyp.get('root_cause', 'N/A')}",
            "",
            "## 3. Candidate Patch Diff (not necessarily applied or verified)",
            f"**Target**: `{patch.get('target_file', 'N/A')}` | **Approval**: {'Approved' if patch.get('is_approved') else 'Pending Approval'}",
            *fenced(patch.get("diff_content") or "# No patch diff available", "diff"),
            "",
            "## 4. Execution Sandbox Evidence",
            f"- **Trust**: `{verif.get('trust_level', 'unverified')}` on `{verif.get('execution_environment', 'unknown')}`",
            f"- **Reproducing tests**: `{', '.join(verif.get('reproducing_test_ids', [])) or 'none recorded'}`",
            f"- **Verification reason**: `{verif.get('reason') or 'not recorded'}`",
            f"- **Baseline Run**: Exit Code `{verif.get('baseline_execution', {}).get('exit_code')}` (Passed: `{verif.get('baseline_execution', {}).get('passed')}`)",
            f"- **Patched Run**: Exit Code `{verif.get('patched_execution', {}).get('exit_code')}` (Passed: `{verif.get('patched_execution', {}).get('passed')}`)",
            f"- **Execution Duration**: `{verif.get('patched_execution', {}).get('duration_seconds')}s`",
            "",
            "### Sandbox Test Output Excerpt",
            *fenced(verif.get("patched_execution", {}).get("stdout_excerpt") or "No output captured", "text"),
            "",
            "## 5. Audit Timeline",
        ])

        for event in report.get("timeline", []):
            md.append(f"- `[{event.get('timestamp')}]` **{event.get('title')}**")

        return "\n".join(md)
