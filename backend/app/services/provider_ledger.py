"""Provider call auditing ledger and atomic database budget enforcement."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import text

from ..core.config import get_settings
from ..database import SessionLocal, engine
from .meta_client import MetaAPIError

logger = logging.getLogger("patchpilot.services.provider_ledger")


def enforce_atomic_budget(
    owner_id: str,
    ip_address: str = "unknown",
    estimated_tokens: int = 0,
    settings=None,
) -> None:
    """Enforce call and token budgets across global daily, session, and IP scopes atomically in DB.

    Raises MetaAPIError with BUDGET_EXHAUSTED if limits are exceeded.
    """
    cfg = settings or get_settings()
    today = datetime.now(timezone.utc).date().isoformat()
    ip_hash = hashlib.sha256(ip_address.encode("utf-8")).hexdigest()[:16]

    # Limits
    global_cap = cfg.PUBLIC_DAILY_META_CALL_CAP
    session_cap = 60
    ip_cap = 30
    token_cap_daily = 500000

    checks = [
        (f"global:{today}", global_cap, token_cap_daily),
        (f"session:{owner_id}:{today}", session_cap, token_cap_daily),
        (f"ip:{ip_hash}:{today}", ip_cap, token_cap_daily),
    ]

    now_iso = datetime.now(timezone.utc).isoformat()

    with engine.begin() as conn:
        for key, max_calls, max_tokens in checks:
            if max_calls <= 0:
                continue
            # Atomic increment-and-check using INSERT ... ON CONFLICT
            res = conn.execute(
                text(
                    """
                    INSERT INTO provider_budget_counters (budget_key, calls, tokens, updated_at)
                    VALUES (:key, 1, :tokens, :now)
                    ON CONFLICT(budget_key) DO UPDATE SET
                        calls = provider_budget_counters.calls + 1,
                        tokens = provider_budget_counters.tokens + :tokens,
                        updated_at = :now
                    WHERE provider_budget_counters.calls < :max_calls
                      AND (provider_budget_counters.tokens + :tokens) <= :max_tokens
                    """
                ),
                {"key": key, "tokens": max(0, estimated_tokens), "now": now_iso, "max_calls": max_calls, "max_tokens": max_tokens},
            )
            if res.rowcount == 0:
                logger.warning("Budget limit exhausted for key=%s (max_calls=%d)", key, max_calls)
                if cfg.LLM_PROVIDER == "replay":
                    logger.info("Falling back to REPLAY provider due to budget limit.")
                    return
                raise MetaAPIError(
                    f"AI request budget exhausted for scope: {key.split(':')[0]}",
                    status_code=429,
                    provider_status="BUDGET_EXHAUSTED",
                )


def record_provider_call(
    owner_id: str,
    provider: str,
    stage: str,
    model: Optional[str] = None,
    prompt: Optional[str] = None,
    response_text: Optional[str] = None,
    latency_ms: Optional[int] = None,
    status: str = "success",
    tokens: Optional[int] = None,
    plan_id: Optional[str] = None,
    patch_id: Optional[str] = None,
    generated_test_id: Optional[str] = None,
    attempt: Optional[int] = None,
) -> str:
    """Record a model invocation in the persistent provider_calls ledger."""
    call_id = str(uuid4())
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt else None
    response_hash = hashlib.sha256(response_text.encode("utf-8")).hexdigest() if response_text else None

    try:
        with SessionLocal(info={"owner_id": owner_id}) as db:
            from ..models.provider_call import ProviderCall

            record = ProviderCall(
                id=call_id,
                owner_id=owner_id,
                provider=provider,
                stage=stage,
                model=model,
                prompt_hash=prompt_hash,
                response_hash=response_hash,
                latency_ms=latency_ms,
                status=status,
                tokens=tokens,
                plan_id=plan_id,
                patch_id=patch_id,
                generated_test_id=generated_test_id,
                attempt=attempt,
            )
            db.add(record)
            db.commit()
    except Exception as exc:
        logger.error("Failed to record provider call in ledger: %s", exc)

    return call_id
