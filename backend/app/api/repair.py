"""Repair verification and bounded self-repair loop API endpoints."""
from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..core.config import get_settings
from ..models.audit_event import AuditEvent
from ..models.generated_test import GeneratedTest
from ..models.patch import Patch
from ..models.project import Project
from ..models.verification_run import VerificationRun
from ..services.repair_loop import RepairLoopOrchestrator
from ..services.reporting import EvidenceReporter
from ..services.verification_engine import VerificationEngine

logger = logging.getLogger("patchpilot.api.repair")
router = APIRouter()

verification_engine = VerificationEngine()
repair_loop = RepairLoopOrchestrator()


class VerifyRequest(BaseModel):
    test_command_target: str = "tests"
    reproducing_test_ids: list[str] = Field(default_factory=list, max_length=100)


class RepairLoopRequest(BaseModel):
    max_attempts: int = 3


@router.post("/patches/{patch_id}/verify")
def verify_patch_endpoint(
    patch_id: str,
    req: VerifyRequest = VerifyRequest(),
    db: Session = Depends(get_db),
):
    """Run an isolated sandbox verification comparing baseline vs patched tests."""
    patch = db.query(Patch).filter(Patch.id == patch_id).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    settings = get_settings()
    if settings.APP_MODE == "public_demo":
        project = db.query(Project).filter(Project.id == patch.project_id).first()
        if not project or not project.is_sample:
            raise HTTPException(status_code=403, detail={"error_code": "PUBLIC_SAMPLE_ONLY",
                "message": "Public demo supports bundled samples only."})
        if req.test_command_target != "tests":
            raise HTTPException(status_code=403, detail={"error_code": "CUSTOM_TEST_SELECTOR_DISABLED",
                "message": "Custom test selectors are disabled on the public demo."})

    # Check for regression tests associated with this patch or project
    reg_test = db.query(GeneratedTest).filter(GeneratedTest.patch_id == patch_id).first()
    reg_code = reg_test.test_code if reg_test else None

    # Run verification in disposable sandbox
    results = verification_engine.verify_patch(
        project_id=patch.project_id,
        target_file=patch.target_file,
        diff_content=patch.diff_content,
        regression_test_code=reg_code,
        test_command_target=req.test_command_target,
        reproducing_test_ids=req.reproducing_test_ids,
    )

    verif_status = results.get("verification_status", "NOT_VERIFIED")
    baseline = results.get("baseline") or {}
    patched = results.get("patched") or {}
    reg_res = results.get("regression_test") or {}

    run_record = VerificationRun(
        id=str(uuid4()),
        project_id=patch.project_id,
        patch_id=patch.id,
        status="completed",
        verification_status=verif_status,
        baseline_passed=baseline.get("passed"),
        baseline_stdout=baseline.get("stdout"),
        baseline_stderr=baseline.get("stderr"),
        baseline_exit_code=baseline.get("exit_code"),
        patched_passed=patched.get("passed"),
        patched_stdout=patched.get("stdout"),
        patched_stderr=patched.get("stderr"),
        patched_exit_code=patched.get("exit_code"),
        regression_test_passed=reg_res.get("passed") if reg_res else None,
        regression_test_stdout=reg_res.get("stdout") if reg_res else None,
        duration_seconds=patched.get("duration_seconds", 0.0),
        details=json.dumps(results),
    )
    db.add(run_record)

    event = AuditEvent(
        id=str(uuid4()),
        project_id=patch.project_id,
        event_type="verification_completed",
        title=f"Patch {patch_id[:8]} verified (Status: {verif_status})",
    )
    db.add(event)

    db.commit()
    db.refresh(run_record)

    return {
        "id": run_record.id,
        "verification_status": run_record.verification_status,
        "reason": results.get("reason"),
        "reproducing_test_ids": results.get("reproducing_test_ids", []),
        "affected_test_ids": results.get("affected_test_ids", []),
        "execution_environment": results.get("execution_environment", "unknown"),
        "trust_level": results.get("trust_level", "unverified"),
        "baseline_passed": run_record.baseline_passed,
        "baseline_exit_code": run_record.baseline_exit_code,
        "patched_passed": run_record.patched_passed,
        "patched_exit_code": run_record.patched_exit_code,
        "regression_test_passed": run_record.regression_test_passed,
        "regression_test_exit_code": (reg_res.get("exit_code") if reg_res else None),
        "duration_seconds": run_record.duration_seconds,
        "baseline_stdout": run_record.baseline_stdout,
        "patched_stdout": run_record.patched_stdout,
        "patched_stderr": run_record.patched_stderr,
    }


@router.get("/verification-runs/{run_id}")
def get_verification_run(run_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a specific verification run."""
    run = db.query(VerificationRun).filter(VerificationRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Verification run not found")
    return run


@router.get("/patches/{patch_id}/verification-history")
def get_verification_history(patch_id: str, db: Session = Depends(get_db)):
    """List historical verification runs for a patch."""
    if db.query(Patch).filter(Patch.id == patch_id).first() is None:
        raise HTTPException(status_code=404, detail="Patch not found")
    return (
        db.query(VerificationRun)
        .filter(VerificationRun.patch_id == patch_id)
        .order_by(VerificationRun.created_at.desc())
        .all()
    )


@router.post("/patches/{patch_id}/repair-loop")
async def execute_repair_loop_endpoint(
    patch_id: str,
    req: RepairLoopRequest = RepairLoopRequest(),
    db: Session = Depends(get_db),
):
    """Execute a bounded repair loop feeding test results back to the selected provider."""
    patch = db.query(Patch).filter(Patch.id == patch_id).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    project = db.query(Project).filter(Project.id == patch.project_id).first()
    if project and (get_settings().DEMO_MODE or get_settings().APP_MODE == "public_demo") and not project.is_sample:
        raise HTTPException(status_code=403, detail={"error_code": "DEMO_UNSUPPORTED_PROJECT",
            "message": "Demo mode only supports the bundled sample project."})
    bug_desc = project.bug_description if project else "Bug fix"

    reg_test = db.query(GeneratedTest).filter(GeneratedTest.patch_id == patch_id).first()
    reg_code = reg_test.test_code if reg_test else None

    loop_result = await repair_loop.execute_repair_loop(
        project_id=patch.project_id,
        target_file=patch.target_file,
        bug_description=bug_desc,
        initial_diff=patch.diff_content,
        regression_test_code=reg_code,
        max_attempts=min(max(1, req.max_attempts),
            get_settings().PUBLIC_MAX_ATTEMPTS if get_settings().APP_MODE == "public_demo"
            else get_settings().MAX_REPAIR_ATTEMPTS),
    )

    # If new successful diff was found, update patch
    if loop_result.get("successful_diff"):
        patch.diff_content = loop_result["successful_diff"]
        patch.validation_status = "valid"

    event = AuditEvent(
        id=str(uuid4()),
        project_id=patch.project_id,
        event_type="repair_loop_iteration",
        title=f"Repair loop finished ({loop_result['attempts_made']} attempts, final: {loop_result['final_status']})",
    )
    db.add(event)
    db.commit()

    return loop_result


reporter = EvidenceReporter()


@router.get("/projects/{project_id}/report")
def get_project_report(
    project_id: str,
    format: str = "json",
    db: Session = Depends(get_db),
):
    """Generate comprehensive evidence report in JSON or Markdown format."""
    report_data = reporter.generate_project_report(db, project_id)
    if "error" in report_data:
        raise HTTPException(status_code=404, detail=report_data["error"])

    if format.lower() == "markdown":
        from fastapi.responses import PlainTextResponse
        md_text = reporter.render_markdown(report_data)
        return PlainTextResponse(content=md_text, media_type="text/markdown")

    return report_data


@router.get("/projects/{project_id}/timeline")
def get_project_timeline(project_id: str, db: Session = Depends(get_db)):
    """Retrieve chronologically ordered audit events for the project."""
    if db.query(Project).filter(Project.id == project_id).first() is None:
        raise HTTPException(status_code=404, detail="Project not found")
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.project_id == project_id)
        .order_by(AuditEvent.created_at.asc())
        .all()
    )
    return events
