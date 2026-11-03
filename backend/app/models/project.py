"""Project ORM model representing uploaded repositories and workspaces."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from ..database import Base, OwnerScoped


class Project(OwnerScoped, Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    bug_description = Column(Text, nullable=True)
    stack_trace = Column(Text, nullable=True)
    language = Column(String, default="python", nullable=False)
    zip_path = Column(String, nullable=True)
    workspace_path = Column(String, nullable=True)
    file_count = Column(Integer, default=0, nullable=False)
    size_bytes = Column(Integer, default=0, nullable=False)
    analysis_status = Column(String, default="pending", nullable=False)
    is_sample = Column(Boolean, default=False, nullable=False)
    # Statuses: pending, analyzing, analyzed, failed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
