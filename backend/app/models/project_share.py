"""Opt-in, read-only project share grants; only token hashes are persisted."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, String

from ..database import Base, OwnerScoped


class ProjectShare(OwnerScoped, Base):
    __tablename__ = "project_shares"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
