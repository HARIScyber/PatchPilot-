"""Verification run ORM model tracking test executions in the sandbox."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from ..database import Base, OwnerScoped


class VerificationRun(OwnerScoped, Base):
    __tablename__ = "verification_runs"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    patch_id = Column(String, ForeignKey("patches.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String, nullable=False, default="queued")
    # Statuses: queued, running, completed, failed, cancelled
    verification_status = Column(String, nullable=False, default="NOT_VERIFIED")
    # Controlled statuses:
    # VERIFIED_AGAINST_DEFINED_TESTS
    # TESTS_FAILED
    # PARTIALLY_VERIFIED
    # NOT_VERIFIED
    # EXECUTION_UNAVAILABLE
    # REQUIRES_HUMAN_REVIEW

    # Execution outputs
    baseline_passed = Column(Boolean, nullable=True)
    baseline_stdout = Column(Text, nullable=True)
    baseline_stderr = Column(Text, nullable=True)
    baseline_exit_code = Column(Integer, nullable=True)

    patched_passed = Column(Boolean, nullable=True)
    patched_stdout = Column(Text, nullable=True)
    patched_stderr = Column(Text, nullable=True)
    patched_exit_code = Column(Integer, nullable=True)

    regression_test_passed = Column(Boolean, nullable=True)
    regression_test_stdout = Column(Text, nullable=True)

    duration_seconds = Column(Float, default=0.0, nullable=False)
    details = Column(Text, nullable=True)  # JSON details
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
