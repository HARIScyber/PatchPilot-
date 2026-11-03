"""Generated test ORM model for regression test suites."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from ..database import Base, OwnerScoped


class GeneratedTest(OwnerScoped, Base):
    __tablename__ = "generated_tests"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    patch_id = Column(String, ForeignKey("patches.id", ondelete="SET NULL"), nullable=True)
    test_file_path = Column(String, nullable=False)
    test_code = Column(Text, nullable=False)
    test_framework = Column(String, nullable=False, default="pytest")
    test_purpose = Column(Text, nullable=True)
    execution_status = Column(String, nullable=False, default="unrun")
    # Statuses: unrun, passed, failed, error
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
