"""Repair session Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RepairStartRequest(BaseModel):
    project_id: str
    bug_description: Optional[str] = Field(
        default=None,
        description="Detailed description of the bug or observed faulty behavior.",
    )
    stack_trace: Optional[str] = Field(
        default=None,
        description="Optional runtime error stack trace or exception traceback.",
    )
    test_command: Optional[str] = Field(
        default=None,
        description="Custom test execution command (e.g., 'pytest tests/test_calc.py').",
    )
    max_attempts: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Max iterative repair loops before completing.",
    )


class TimelineEvent(BaseModel):
    step: str
    timestamp: str
    title: str
    description: str
    status: str  # in_progress, success, failure, info
    data: Optional[Dict[str, Any]] = None


class TestRunOutput(BaseModel):
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0


class EvidenceReport(BaseModel):
    summary: str
    root_cause_analysis: str
    suspected_files: List[str] = Field(default_factory=list)
    reproduced_failure: Optional[str] = None
    regression_test_code: Optional[str] = None
    patch_diff: Optional[str] = None
    verification_status: str  # verified, failed, not_verified, execution_unavailable
    attempts_made: int
    confidence_score: float = 0.0
    timeline: List[TimelineEvent] = Field(default_factory=list)
    test_evidence: Optional[Dict[str, Any]] = None


class RepairResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    status: str
    verification_status: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    bug_summary: Optional[str] = None
    root_cause: Optional[str] = None
    patch_diff: Optional[str] = None
    test_results: Optional[str] = None
    report: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
