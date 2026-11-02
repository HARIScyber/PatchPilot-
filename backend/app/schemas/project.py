"""Project Pydantic schemas for request/response validation."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    name: str
    bug_description: Optional[str] = None
    stack_trace: Optional[str] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    language: str = "python"
    file_count: int = 0
    size_bytes: int = 0
    analysis_status: str = "pending"
    bug_description: Optional[str] = None
    stack_trace: Optional[str] = None
    is_sample: bool = False
    created_at: datetime
