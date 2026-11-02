"""Repair session ORM model."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from ..database import Base


class Repair(Base):
    __tablename__ = "repairs"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="pending")
    # One of: pending, investigating, patching, testing, verified, failed,
    #         not_verified, execution_unavailable, requires_human_review
    verification_status = Column(String, nullable=True)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    bug_summary = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    patch_diff = Column(Text, nullable=True)
    test_results = Column(Text, nullable=True)  # JSON blob
    report = Column(Text, nullable=True)  # JSON blob
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
