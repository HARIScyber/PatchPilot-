"""Patch ORM model tracking generated unified diffs and approval states."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text

from ..database import Base, OwnerScoped


class Patch(OwnerScoped, Base):
    __tablename__ = "patches"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(String, ForeignKey("repair_plans.id", ondelete="SET NULL"), nullable=True)
    finding_id = Column(String, ForeignKey("findings.id", ondelete="SET NULL"), nullable=True)
    target_file = Column(String, nullable=False)
    original_file_hash = Column(String, nullable=True)
    diff_content = Column(Text, nullable=False)
    model_id = Column(String, nullable=True, default=None)
    validation_status = Column(String, nullable=False, default="pending")
    # Statuses: pending, valid, invalid, rejected
    validation_error = Column(Text, nullable=True)
    is_approved = Column(Boolean, default=False, nullable=False)
    is_applied = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
