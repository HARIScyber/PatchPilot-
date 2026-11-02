"""Repair plan ORM model."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from ..database import Base


class RepairPlan(Base):
    __tablename__ = "repair_plans"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    finding_id = Column(String, ForeignKey("findings.id", ondelete="SET NULL"), nullable=True)
    problem_summary = Column(Text, nullable=False)
    root_cause = Column(Text, nullable=False)
    evidence = Column(Text, nullable=True)
    candidate_files = Column(Text, nullable=False)  # JSON serialized list of files
    proposed_changes = Column(Text, nullable=False)  # JSON serialized ordered steps
    expected_behavior = Column(Text, nullable=False)
    regression_test_plan = Column(Text, nullable=True)
    risks_and_assumptions = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
