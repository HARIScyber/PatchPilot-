"""Provider call ledger and budget counter ORM models."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from ..database import Base, OwnerScoped


class ProviderCall(OwnerScoped, Base):
    __tablename__ = "provider_calls"

    id = Column(String, primary_key=True, index=True)
    provider = Column(String, nullable=False, index=True)  # meta_ai, gemini, replay, demo
    stage = Column(String, nullable=False, index=True)     # plan, patch, test_gen, repair_loop
    model = Column(String, nullable=True)                  # Model reported by provider response
    prompt_hash = Column(String(64), nullable=True, index=True)
    response_hash = Column(String(64), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="success")  # success, error, budget_exhausted
    tokens = Column(Integer, nullable=True)                # Total tokens only if supplied
    plan_id = Column(String, ForeignKey("repair_plans.id", ondelete="SET NULL"), nullable=True, index=True)
    patch_id = Column(String, ForeignKey("patches.id", ondelete="SET NULL"), nullable=True, index=True)
    generated_test_id = Column(String, ForeignKey("generated_tests.id", ondelete="SET NULL"), nullable=True, index=True)
    attempt = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class ProviderBudgetCounter(Base):
    __tablename__ = "provider_budget_counters"

    budget_key = Column(String(128), primary_key=True, index=True)
    calls = Column(Integer, nullable=False, default=0)
    tokens = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
