"""Audit event ORM model recording structured timeline events."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from ..database import Base, OwnerScoped


class AuditEvent(OwnerScoped, Base):
    __tablename__ = "audit_events"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    # Types: project_created, zip_uploaded, analysis_started, analysis_completed,
    #        plan_generated, patch_generated, patch_approved, patch_applied,
    #        verification_started, verification_completed, repair_loop_iteration
    title = Column(String, nullable=False)
    details = Column(Text, nullable=True)  # JSON serialized metadata (no secrets!)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
