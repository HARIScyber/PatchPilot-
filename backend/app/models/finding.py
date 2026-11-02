"""Analysis finding ORM model for static inspection and bug localization."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from ..database import Base


class Finding(Base):
    __tablename__ = "findings"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    finding_type = Column(String, nullable=False, index=True)
    # Types: syntax_error, mutable_default, suspicious_exception, shell_injection_risk,
    #        unreachable_code, missing_tests, bug_localization_candidate
    severity = Column(String, nullable=False, default="medium")
    # Severities: critical, high, medium, low, info
    file_path = Column(String, nullable=False)
    line_number = Column(Integer, nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    code_snippet = Column(Text, nullable=True)
    confidence = Column(Float, default=0.7, nullable=False)
    recommended_action = Column(Text, nullable=True)
    is_confirmed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
