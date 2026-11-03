"""Evidence reporting Pydantic schemas."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


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
