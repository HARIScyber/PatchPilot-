"""Patch management, validation, approval, and regression test generation endpoints."""
from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..core.config import get_settings
from ..models.audit_event import AuditEvent
from ..models.finding import Finding
from ..models.generated_test import GeneratedTest
from ..models.patch import Patch
from ..models.project import Project
from ..models.repair_plan import RepairPlan
from ..services.patcher import Patcher, PatchValidationError
from ..services.launch_readiness import public_ai_is_ready
from ..services.repo_manager import RepoManager
from ..services.repair_planner import RepairPlanner
from ..services.test_generator import RegressionTestGenerator

logger = logging.getLogger("patchpilot.api.patches")
router = APIRouter()

repo_manager = RepoManager()
patcher = Patcher()
planner = RepairPlanner()
test_gen = RegressionTestGenerator()


def _require_supported_demo_project(project: Project) -> None:
    settings = get_settings()
    if settings.APP_MODE == "public_demo" and not public_ai_is_ready(settings):
        raise HTTPException(status_code=503, detail={"error_code": "PUBLIC_DEMO_DISABLED",
            "message": "Public repair runs are temporarily disabled."})
    if (settings.DEMO_MODE or settings.APP_MODE == "public_demo") and not project.is_sample:
        raise HTTPException(status_code=403, detail={"error_code": "DEMO_UNSUPPORTED_PROJECT",
            "message": "This mode only supports bundled sample projects."})


class PlanRequest(BaseModel):
    finding_id: Optional[str] = None
    bug_description: Optional[str] = None
    stack_trace: Optional[str] = None


class PatchGenerateRequest(BaseModel):
    plan_id: Optional[str] = None
    target_file: Optional[str] = None


@router.post("/projects/{project_id}/repair-plan")
async def create_repair_plan(
    project_id: str,
    req: PlanRequest,
    db: Session = Depends(get_db),
):
    """Generate a structured AI repair plan for a defect or finding."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _require_supported_demo_project(project)

    finding_context = None
    if req.finding_id:
        f = db.query(Finding).filter(Finding.id == req.finding_id).first()
        if f:
            finding_context = {
                "id": f.id,
                "type": f.finding_type,
                "title": f.title,
                "file_path": f.file_path,
                "line_number": f.line_number,
                "description": f.description,
            }

    desc = req.bug_description or (finding_context.get("description") if finding_context else project.bug_description) or "Bug fix"
    trace = req.stack_trace or project.stack_trace

    # Read relevant source snippet if finding available
    source_context = None
    if finding_context and finding_context.get("file_path"):
        try:
            content_data = repo_manager.read_file_content(project_id, finding_context["file_path"])
            source_context = content_data.get("content")
        except Exception:
            pass

    plan = await planner.generate_plan(
        project_id=project_id,
        bug_description=desc,
        stack_trace=trace,
        finding_context=finding_context,
        source_context=source_context,
    )

    plan_record = RepairPlan(
        id=str(uuid4()),
        project_id=project_id,
        finding_id=req.finding_id,
        problem_summary=plan.problem_summary,
        root_cause=plan.root_cause,
        evidence=plan.evidence,
        candidate_files=json.dumps(plan.candidate_files),
        proposed_changes=json.dumps(plan.proposed_changes),
        expected_behavior=plan.expected_behavior,
        regression_test_plan=plan.regression_test_plan,
        risks_and_assumptions=plan.risks_and_assumptions,
    )
    db.add(plan_record)

    event = AuditEvent(
        id=str(uuid4()),
        project_id=project_id,
        event_type="plan_generated",
        title=f"Repair plan generated: {plan.problem_summary[:60]}...",
    )
    db.add(event)

    db.commit()
    db.refresh(plan_record)

    return {
        "id": plan_record.id,
        "problem_summary": plan_record.problem_summary,
        "root_cause": plan_record.root_cause,
        "evidence": plan_record.evidence,
        "candidate_files": json.loads(plan_record.candidate_files),
        "proposed_changes": json.loads(plan_record.proposed_changes),
        "expected_behavior": plan_record.expected_behavior,
        "regression_test_plan": plan_record.regression_test_plan,
        "risks_and_assumptions": plan_record.risks_and_assumptions,
        "created_at": plan_record.created_at,
    }


@router.post("/projects/{project_id}/patches/generate")
async def generate_patch(
    project_id: str,
    req: PatchGenerateRequest,
    db: Session = Depends(get_db),
):
    """Generate a unified diff patch based on a repair plan."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _require_supported_demo_project(project)

    plan = None
    if req.plan_id:
        plan = db.query(RepairPlan).filter(
            RepairPlan.id == req.plan_id,
            RepairPlan.project_id == project_id,
        ).first()
        if not plan:
            raise HTTPException(status_code=404, detail="Repair plan not found for this project")
    if not plan:
        # Fallback to latest plan for project
        plan = db.query(RepairPlan).filter(RepairPlan.project_id == project_id).order_by(RepairPlan.created_at.desc()).first()

    if not plan:
        raise HTTPException(status_code=400, detail="No repair plan found. Generate a repair plan first.")

    candidate_files = json.loads(plan.candidate_files)
    target_file = req.target_file or (candidate_files[0] if candidate_files else "core/calculator.py")
    proposed_changes = json.loads(plan.proposed_changes)

    workspace = repo_manager.get_workspace_dir(project_id)
    try:
        full_target = patcher.resolve_target_file(workspace, target_file)
    except PatchValidationError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    orig_hash = patcher.compute_file_hash(full_target) if full_target.is_file() else None

    # Generate unified diff
    diff_content = await patcher.generate_patch(
        project_id=project_id,
        target_file_rel=target_file,
        problem_summary=plan.problem_summary,
        root_cause=plan.root_cause,
        proposed_changes=proposed_changes,
    )

    # Validate against temporary snapshot
    is_valid, val_err, _ = patcher.parse_and_validate_diff(workspace, diff_content, target_file)

    patch_record = Patch(
        id=str(uuid4()),
        project_id=project_id,
        plan_id=plan.id,
        finding_id=plan.finding_id,
        target_file=target_file,
        original_file_hash=orig_hash,
        diff_content=diff_content,
        validation_status="valid" if is_valid else "invalid",
        validation_error=val_err,
        is_approved=False,
        is_applied=False,
    )
    db.add(patch_record)

    event = AuditEvent(
        id=str(uuid4()),
        project_id=project_id,
        event_type="patch_generated",
        title=f"Candidate patch created for '{target_file}' (Status: {patch_record.validation_status})",
    )
    db.add(event)

    db.commit()
    db.refresh(patch_record)

    return patch_record


@router.get("/projects/{project_id}/patches")
def list_project_patches(project_id: str, db: Session = Depends(get_db)):
    """List all generated patches for a project."""
    return db.query(Patch).filter(Patch.project_id == project_id).order_by(Patch.created_at.desc()).all()


@router.get("/patches/{patch_id}")
def get_patch(patch_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a specific patch."""
    patch = db.query(Patch).filter(Patch.id == patch_id).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")
    return patch


@router.post("/patches/{patch_id}/validate")
def validate_patch(patch_id: str, db: Session = Depends(get_db)):
    """Run dry-run diff application and AST syntax validation against a temporary snapshot."""
    patch = db.query(Patch).filter(Patch.id == patch_id).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    workspace = repo_manager.get_workspace_dir(patch.project_id)
    is_valid, err_msg, _ = patcher.parse_and_validate_diff(workspace, patch.diff_content, patch.target_file)

    patch.validation_status = "valid" if is_valid else "invalid"
    patch.validation_error = err_msg
    db.commit()

    return {
        "status": patch.validation_status,
        "is_valid": is_valid,
        "validation_error": patch.validation_error,
    }


@router.post("/patches/{patch_id}/approve")
def approve_patch(patch_id: str, db: Session = Depends(get_db)):
    """Human-in-the-loop approval of candidate patch."""
    patch = db.query(Patch).filter(Patch.id == patch_id).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    workspace = repo_manager.get_workspace_dir(patch.project_id)
    is_valid, err_msg, _ = patcher.parse_and_validate_diff(workspace, patch.diff_content, patch.target_file)
    if not is_valid:
        patch.validation_status = "invalid"
        patch.validation_error = err_msg
        db.commit()
        raise HTTPException(status_code=409, detail=f"Patch must validate before approval: {err_msg}")
    patch.validation_status = "valid"
    patch.validation_error = None

    patch.is_approved = True
    event = AuditEvent(
        id=str(uuid4()),
        project_id=patch.project_id,
        event_type="patch_approved",
        title=f"Patch {patch_id} approved for target '{patch.target_file}'",
    )
    db.add(event)
    db.commit()
    return {"status": "success", "message": "Patch approved", "is_approved": True}


@router.post("/patches/{patch_id}/reject")
def reject_patch(patch_id: str, db: Session = Depends(get_db)):
    """Reject candidate patch."""
    patch = db.query(Patch).filter(Patch.id == patch_id).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    patch.is_approved = False
    patch.validation_status = "rejected"
    db.commit()
    return {"status": "success", "message": "Patch rejected", "validation_status": "rejected"}


@router.post("/patches/{patch_id}/apply")
def apply_patch(patch_id: str, db: Session = Depends(get_db)):
    """Apply approved patch to workspace. Requires explicit approval."""
    patch = db.query(Patch).filter(Patch.id == patch_id).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    if not patch.is_approved:
        raise HTTPException(
            status_code=400,
            detail="Patch must be explicitly approved by human reviewer before applying to workspace.",
        )

    workspace = repo_manager.get_workspace_dir(patch.project_id)
    try:
        target_file = patcher.resolve_target_file(workspace, patch.target_file)
        if not patch.original_file_hash or patcher.compute_file_hash(target_file) != patch.original_file_hash:
            raise HTTPException(status_code=409, detail="Target file changed since patch generation; regenerate and review the patch.")
        patcher.apply_patch_to_workspace(workspace, patch.diff_content, patch.target_file)
        patch.is_applied = True
        event = AuditEvent(
            id=str(uuid4()),
            project_id=patch.project_id,
            event_type="patch_applied",
            title=f"Patch {patch_id} permanently applied to workspace '{patch.target_file}'",
        )
        db.add(event)
        db.commit()
        return {"status": "success", "message": f"Patch applied to {patch.target_file}"}
    except PatchValidationError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.post("/patches/{patch_id}/generate-tests")
async def generate_regression_tests(patch_id: str, db: Session = Depends(get_db)):
    """Generate pytest regression test suite for a candidate patch."""
    patch = db.query(Patch).filter(Patch.id == patch_id).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    project = db.query(Project).filter(Project.id == patch.project_id).first()
    if project:
        _require_supported_demo_project(project)
    bug_desc = project.bug_description if project else "Bug fix"

    test_code = await test_gen.generate_regression_test(
        bug_description=bug_desc,
        target_file=patch.target_file,
        patch_diff=patch.diff_content,
    )

    test_record = GeneratedTest(
        id=str(uuid4()),
        project_id=patch.project_id,
        patch_id=patch.id,
        test_file_path=f"tests/test_regression_{patch.id[:8]}.py",
        test_code=test_code,
        test_framework="pytest",
        test_purpose="Verify fix of defect boundary condition and prevent regressions.",
        execution_status="unrun",
    )
    db.add(test_record)

    event = AuditEvent(
        id=str(uuid4()),
        project_id=patch.project_id,
        event_type="test_generated",
        title=f"Regression test suite generated ({test_record.test_file_path})",
    )
    db.add(event)

    db.commit()
    db.refresh(test_record)

    return test_record
