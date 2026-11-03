"""Project management and repository intake API endpoints."""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..core.config import get_settings
from ..models.audit_event import AuditEvent
from ..models.finding import Finding
from ..models.project import Project
from ..schemas.project import ProjectCreate, ProjectResponse
from ..security.zip_validator import ZipSecurityError
from ..services.localization import BugLocalizer
from ..services.repo_manager import RepoManager
from ..services.static_analyzer import analyze_repository

logger = logging.getLogger("patchpilot.api.projects")
router = APIRouter()
repo_manager = RepoManager()
SAMPLE_PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent / "sample_data" / "calculator_bug"


def _require_bundled_sample(project: Project) -> None:
    if get_settings().APP_MODE == "public_demo" and not project.is_sample:
        raise HTTPException(status_code=404, detail={"error_code": "PUBLIC_SAMPLE_ONLY",
            "message": "This project is not available in the public demo."})


@router.post("/", response_model=ProjectResponse)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    """Create a new project record."""
    settings = get_settings()
    if settings.APP_MODE == "public_demo":
        raise HTTPException(status_code=403, detail={"error_code": "PUBLIC_SAMPLE_ONLY",
            "message": "Public demo supports bundled sample projects only."})
    project_id = str(uuid4())
    workspace = repo_manager.create_workspace(project_id)

    project = Project(
        id=project_id,
        name=data.name,
        bug_description=data.bug_description,
        stack_trace=data.stack_trace,
        workspace_path=str(workspace),
        analysis_status="pending",
    )
    db.add(project)
    db.flush()

    event = AuditEvent(
        id=str(uuid4()),
        project_id=project_id,
        event_type="project_created",
        title=f"Project '{data.name}' initialized",
    )
    db.add(event)

    db.commit()
    db.refresh(project)
    return project


@router.get("/", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    """List all projects ordered by newest first."""
    query = db.query(Project)
    if get_settings().APP_MODE == "public_demo":
        query = query.filter(Project.is_sample.is_(True))
    return query.order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a single project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    _require_bundled_sample(project)
    return project


@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    """Delete a project and its on-disk workspace."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _require_bundled_sample(project)

    repo_manager.delete_workspace(project_id)
    db.delete(project)
    db.commit()
    return {"status": "success", "message": f"Project {project_id} deleted"}


@router.post("/{project_id}/upload")
def upload_repository_zip(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload and safely unpack a ZIP archive into the project workspace."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if get_settings().APP_MODE == "public_demo" or not get_settings().ENABLE_UPLOAD:
        raise HTTPException(status_code=403, detail={"error_code": "UPLOAD_DISABLED",
            "message": "Repository uploads are disabled on this deployment."})

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip archives are supported.")

    # Save temp zip
    fd, temp_name = tempfile.mkstemp(prefix="patchpilot-upload-", suffix=".zip", dir=repo_manager.workspaces_root)
    os.close(fd)
    temp_zip = Path(temp_name)
    try:
        with open(temp_zip, "wb") as out_f:
            total = 0
            limit = get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > limit:
                    raise HTTPException(status_code=413, detail="Upload exceeds configured size limit.")
                out_f.write(chunk)

        # Secure extraction
        extracted_info = repo_manager.unpack_archive(project_id, temp_zip)

        project.zip_path = str(temp_zip)
        project.file_count = extracted_info["file_count"]
        project.size_bytes = extracted_info["size_bytes"]
        project.workspace_path = extracted_info["workspace_path"]
        project.analysis_status = "pending"

        event = AuditEvent(
            id=str(uuid4()),
            project_id=project_id,
            event_type="zip_uploaded",
            title=f"Repository archive unpacked ({project.file_count} files, {project.size_bytes} bytes)",
        )
        db.add(event)
        db.commit()

        return {
            "status": "success",
            "file_count": project.file_count,
            "size_bytes": project.size_bytes,
        }

    except ZipSecurityError as sec_err:
        raise HTTPException(status_code=400, detail=f"Security violation: {str(sec_err)}")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Repository extraction failed")
        raise HTTPException(status_code=500, detail="Repository extraction failed.")
    finally:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except OSError:
                pass


@router.post("/load-sample", response_model=ProjectResponse)
def load_sample_project(db: Session = Depends(get_db)):
    """One-click demo loader: unpacks sample buggy calculator project."""
    project_id = str(uuid4())
    if not SAMPLE_PROJECT_DIRECTORY.is_dir():
        raise HTTPException(status_code=503, detail={
            "error_code": "SAMPLE_NOT_FOUND",
            "message": "The bundled sample project is unavailable in this deployment.",
        })
    try:
        extracted_info = repo_manager.copy_bundled_directory(project_id, SAMPLE_PROJECT_DIRECTORY)
    except (OSError, ValueError) as exc:
        logger.error("Bundled sample could not be loaded (%s).", type(exc).__name__)
        repo_manager.delete_workspace(project_id)
        raise HTTPException(status_code=500, detail={
            "error_code": "SAMPLE_LOAD_FAILED",
            "message": "The bundled sample project could not be prepared.",
        }) from exc

    project = Project(
        id=project_id,
        name="Calculator Accumulator Bug (Demo)",
        bug_description=("A cumulative calculation returns an unexpected result for a multi-item input."
            if get_settings().APP_MODE == "public_demo" else
            "Off-by-one error in compute_cumulative_total: fails to include the final item in the summation, "
            "causing test_cumulative_total_inclusive to fail."),
        stack_trace=(
            'Traceback (most recent call last):\n'
            '  File "tests/test_calculator.py", line 22, in test_cumulative_total_inclusive\n'
            '    assert result == 60.0, f"Expected 60.0 but got {result}"\n'
            'AssertionError: Expected 60.0 but got 30.0'
        ),
        workspace_path=extracted_info["workspace_path"],
        file_count=extracted_info["file_count"],
        size_bytes=extracted_info["size_bytes"],
        analysis_status="pending",
        is_sample=True,
    )
    db.add(project)
    db.flush()

    event = AuditEvent(
        id=str(uuid4()),
        project_id=project_id,
        event_type="sample_loaded",
        title="Sample demo project loaded (Calculator Accumulator Bug)",
    )
    db.add(event)

    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}/files")
def get_project_files(project_id: str, db: Session = Depends(get_db)):
    """Return file tree for the project workspace."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _require_bundled_sample(project)

    return repo_manager.get_file_tree(project_id)


@router.get("/{project_id}/files/content")
def get_file_content(
    project_id: str,
    path: str = Query(..., description="Relative file path within workspace"),
    db: Session = Depends(get_db),
):
    """Return the text content of a workspace file."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _require_bundled_sample(project)

    try:
        return repo_manager.read_file_content(project_id, path)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File '{path}' not found")


@router.post("/{project_id}/analyze")
def analyze_project(project_id: str, db: Session = Depends(get_db)):
    """Execute static inspection and bug localization without running untrusted code."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _require_bundled_sample(project)

    workspace = repo_manager.get_workspace_dir(project_id)
    if not workspace.exists():
        raise HTTPException(status_code=400, detail="Workspace does not exist or has not been unpacked.")

    project.analysis_status = "analyzing"
    db.commit()

    try:
        # Clear previous findings
        db.query(Finding).filter(Finding.project_id == project_id).delete()

        # 1. Run AST Static Analysis
        ast_findings = analyze_repository(workspace)

        # 2. Run Bug Localization
        localizer = BugLocalizer(workspace)
        localized = localizer.rank_candidates(
            bug_description=project.bug_description,
            stack_trace=project.stack_trace,
            static_findings=ast_findings,
        )

        # Store all findings
        stored_findings = []
        for f_data in ast_findings + localized:
            finding = Finding(
                id=f_data["id"],
                project_id=project_id,
                finding_type=f_data["finding_type"],
                severity=f_data["severity"],
                file_path=f_data["file_path"],
                line_number=f_data.get("line_number"),
                title=f_data["title"],
                description=f_data["description"],
                code_snippet=f_data.get("code_snippet"),
                confidence=f_data.get("confidence", 0.7),
                recommended_action=f_data.get("recommended_action"),
                is_confirmed=f_data.get("is_confirmed", False),
            )
            db.add(finding)
            stored_findings.append(finding)

        project.analysis_status = "analyzed"

        event = AuditEvent(
            id=str(uuid4()),
            project_id=project_id,
            event_type="analysis_completed",
            title=f"Analysis completed: {len(stored_findings)} findings identified",
        )
        db.add(event)

        db.commit()

        return {
            "status": "success",
            "findings_count": len(stored_findings),
            "findings": [
                {
                    "id": f.id,
                    "finding_type": f.finding_type,
                    "severity": f.severity,
                    "file_path": f.file_path,
                    "line_number": f.line_number,
                    "title": f.title,
                    "description": f.description,
                    "code_snippet": f.code_snippet,
                    "confidence": f.confidence,
                    "recommended_action": f.recommended_action,
                }
                for f in stored_findings
            ],
        }

    except Exception as exc:
        project.analysis_status = "failed"
        db.commit()
        logger.exception("Analysis failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(exc)}")


@router.get("/{project_id}/findings")
def get_project_findings(project_id: str, db: Session = Depends(get_db)):
    """List all persisted findings for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _require_bundled_sample(project)
    findings = db.query(Finding).filter(Finding.project_id == project_id).all()
    return findings
