"""Repository management service for workspace allocation, file tree indexing, and safe content access."""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from ..core.config import get_settings
from ..security.zip_validator import validate_and_extract_zip

logger = logging.getLogger("patchpilot.services.repo_manager")

EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".tox",
}

EXCLUDED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dll",
    ".exe",
    ".bin",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
}

MAX_FILE_READ_BYTES = 500 * 1024  # 500 KB limit for web view


class RepoManager:
    """Manages project workspaces on disk."""

    def __init__(self):
        settings = get_settings()
        self.workspaces_root = Path(settings.DATABASE_URL.replace("sqlite:///", "")).parent / "workspaces"
        self.workspaces_root.mkdir(parents=True, exist_ok=True)

    def get_workspace_dir(self, project_id: str) -> Path:
        """Return the dedicated workspace path for a project."""
        workspace = (self.workspaces_root / project_id).resolve()
        # Security: verify it stays under workspaces_root
        try:
            workspace.relative_to(self.workspaces_root.resolve())
        except ValueError:
            raise ValueError(f"Invalid workspace path for project {project_id}")
        return workspace

    def create_workspace(self, project_id: str) -> Path:
        """Create and return an empty workspace directory."""
        workspace = self.get_workspace_dir(project_id)
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    def delete_workspace(self, project_id: str) -> None:
        """Safely remove a project's workspace directory."""
        workspace = self.get_workspace_dir(project_id)
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)
            logger.info("Removed workspace for project %s", project_id)

    def unpack_archive(self, project_id: str, zip_path: Path | str) -> Dict[str, Any]:
        """Validate and extract to a sibling staging directory, then replace atomically."""
        workspace = self.get_workspace_dir(project_id)
        workspace.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{project_id}-", dir=workspace.parent))
        try:
            extracted_files = validate_and_extract_zip(zip_path, staging)
            entries = list(staging.iterdir())
            if len(entries) == 1 and entries[0].is_dir():
                nested = entries[0]
                flattened = staging.with_name(staging.name + "-flat")
                nested.rename(flattened)
                shutil.rmtree(staging)
                staging = flattened
                extracted_files = [str(p) for p in staging.rglob("*") if p.is_file()]
            old = workspace.with_name(workspace.name + ".old")
            if old.exists():
                shutil.rmtree(old)
            if workspace.exists():
                workspace.rename(old)
            try:
                staging.rename(workspace)
            except Exception:
                if old.exists() and not workspace.exists():
                    old.rename(workspace)
                raise
            if old.exists():
                shutil.rmtree(old)
            extracted_files = [str(workspace / Path(p).relative_to(staging)) for p in extracted_files]
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise

        total_size = sum(os.path.getsize(f) for f in extracted_files if os.path.exists(f))
        return {
            "workspace_path": str(workspace),
            "file_count": len(extracted_files),
            "size_bytes": total_size,
        }

    def copy_bundled_directory(self, project_id: str, source_path: Path | str) -> Dict[str, Any]:
        """Copy trusted, packaged sample source into a fresh project workspace."""
        source = Path(source_path).resolve()
        if not source.is_dir():
            raise FileNotFoundError("Bundled sample directory is unavailable.")
        workspace = self.create_workspace(project_id)
        try:
            for item in source.iterdir():
                if item.is_symlink():
                    raise ValueError("Bundled sample must not contain symlinks.")
                destination = workspace / item.name
                if item.is_dir():
                    shutil.copytree(item, destination)
                else:
                    shutil.copy2(item, destination)
            files = [path for path in workspace.rglob("*") if path.is_file()]
            return {
                "workspace_path": str(workspace),
                "file_count": len(files),
                "size_bytes": sum(path.stat().st_size for path in files),
            }
        except Exception:
            self.delete_workspace(project_id)
            raise

    def get_file_tree(self, project_id: str) -> List[Dict[str, Any]]:
        """Return a structured tree of files inside the project workspace."""
        workspace = self.get_workspace_dir(project_id)
        if not workspace.exists():
            return []

        tree: List[Dict[str, Any]] = []

        for root, dirs, files in os.walk(workspace):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]

            rel_root = os.path.relpath(root, workspace)
            if rel_root == ".":
                rel_root = ""

            for file_name in files:
                ext = os.path.splitext(file_name)[1].lower()
                if ext in EXCLUDED_EXTENSIONS:
                    continue

                full_path = Path(root) / file_name
                rel_path = (Path(rel_root) / file_name).as_posix() if rel_root else file_name

                try:
                    size = full_path.stat().st_size
                except OSError:
                    size = 0

                tree.append({
                    "path": rel_path,
                    "name": file_name,
                    "extension": ext.lstrip("."),
                    "size_bytes": size,
                    "directory": rel_root.replace("\\", "/") if rel_root else "",
                })

        tree.sort(key=lambda item: item["path"])
        return tree

    def read_file_content(self, project_id: str, relative_path: str) -> Dict[str, Any]:
        """Safely read the content of a file within the project workspace."""
        workspace = self.get_workspace_dir(project_id)
        # Prevent traversal
        clean_rel = relative_path.lstrip("/\\")
        target_file = (workspace / clean_rel).resolve()

        if not target_file.is_relative_to(workspace.resolve()):
            raise ValueError("Path traversal attempt detected.")

        if not target_file.exists() or not target_file.is_file():
            raise FileNotFoundError(f"File '{relative_path}' not found in project workspace.")

        size = target_file.stat().st_size
        if size > MAX_FILE_READ_BYTES:
            return {
                "path": relative_path,
                "content": f"[File size ({size} bytes) exceeds preview limit of {MAX_FILE_READ_BYTES} bytes]",
                "truncated": True,
                "size_bytes": size,
            }

        try:
            with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {
                "path": relative_path,
                "content": content,
                "truncated": False,
                "size_bytes": size,
            }
        except Exception as exc:
            return {
                "path": relative_path,
                "content": f"[Error reading file: {str(exc)}]",
                "truncated": True,
                "size_bytes": size,
            }
