"""Meta AI Model API client with verifiable health checking, live/demo mode separation, and retry logic."""
from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional

import httpx

from ..core.config import get_settings
from ..database import engine
from sqlalchemy import text
from .launch_readiness import public_ai_is_ready

logger = logging.getLogger("patchpilot.services.meta_client")
_shared_http_client = None


def set_shared_http_client(client) -> None:
    global _shared_http_client
    _shared_http_client = client


def get_shared_http_client():
    return _shared_http_client


class MetaAPIError(Exception):
    """Base exception for Meta API failures."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        provider_status: str = "PROVIDER_UNAVAILABLE",
    ):
        # Ensure credentials never leak into exception messages
        settings = get_settings()
        keys = [settings.effective_api_key, settings.GEMINI_API_KEY.get_secret_value()]
        for key in keys:
            if key:
                message = message.replace(key, "***redacted***")
        super().__init__(message)
        self.status_code = status_code
        # Provider bodies can echo request data; never persist/return them.
        self.response_body = None
        self.provider_status = provider_status


class MetaClient:
    """Client for dev.meta.ai Meta Model API (Muse Spark)."""

    def __init__(self, settings=None, http_client=None):
        self._settings = settings
        self.http_client = http_client or _shared_http_client

    @property
    def settings(self):
        return self._settings or get_settings()

    @settings.setter
    def settings(self, value):
        self._settings = value

    async def _post(self, url, *, headers, json, timeout):
        client = self.http_client or _shared_http_client
        if client is not None:
            return await client.post(url, headers=headers, json=json, timeout=timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.post(url, headers=headers, json=json)

    def _reserve_public_call(self) -> None:
        """Atomically consume one UTC-day public call from the local SQLite counter."""
        cap = self.settings.PUBLIC_DAILY_META_CALL_CAP
        if cap <= 0:
            raise MetaAPIError("Daily public Meta call limit has been reached.", 429,
                               provider_status="PUBLIC_DAILY_CAP_EXHAUSTED")
        usage_day = datetime.now(timezone.utc).date().isoformat()
        with engine.begin() as connection:
            result = connection.execute(text("""INSERT INTO public_meta_daily_usage (usage_day, calls)
                VALUES (:usage_day, 1)
                ON CONFLICT(usage_day) DO UPDATE SET calls=calls+1 WHERE calls < :cap"""),
                {"usage_day": usage_day, "cap": cap})
        if result.rowcount == 0:
            raise MetaAPIError("Daily public Meta call limit has been reached.", 429,
                               provider_status="PUBLIC_DAILY_CAP_EXHAUSTED")

    async def check_provider_health(self) -> Dict[str, Any]:
        """Test actual connectivity to Meta Model API and return standardized status.

        Provider states:
        - LIVE_CONNECTED: Real request successfully returned 200 OK
        - NOT_CONFIGURED: No API key set and not in demo mode
        - AUTHENTICATION_FAILED: Key was rejected by Meta (401/403)
        - RATE_LIMITED: Quota or rate limit exceeded (429)
        - PROVIDER_UNAVAILABLE: Connection failure, DNS error, or 5xx from Meta
        - DEMO_MODE: Explicitly running in simulated demo mode
        """
        if self.settings.LLM_PROVIDER == "gemini":
            from .gemini_client import GeminiClient
            return await GeminiClient(self.settings, self.http_client).check_provider_health()
        if self.settings.LLM_PROVIDER == "replay":
            return {"status": "NOT_CONFIGURED", "connected": False, "provider": "replay",
                    "model_id": None, "message": "No replay cassette is configured."}
        if self.settings.LLM_PROVIDER == "demo" or self.settings.DEMO_MODE:
            return {
                "status": "DEMO_MODE",
                "connected": False,
                "is_mock": True,
                "model_id": self.settings.META_MODEL_ID,
                "message": "Demo mode is active (simulated AI output). Live Meta API calls are disabled.",
            }

        api_key = self.settings.effective_api_key
        if not api_key:
            return {
                "status": "NOT_CONFIGURED",
                "connected": False,
                "is_mock": False,
                "model_id": self.settings.META_MODEL_ID,
                "message": "MODEL_API_KEY is not configured in backend/.env. Live AI generation is unavailable.",
            }

        # Perform minimal ping request to dev.meta.ai chat completions
        url = f"{self.settings.META_API_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PatchPilot/1.0",
        }
        test_payload = {
            "model": self.settings.META_MODEL_ID,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }

        start_t = time.time()
        try:
            if self.settings.APP_MODE == "public_demo":
                self._reserve_public_call()
            resp = await self._post(url, headers=headers, json=test_payload, timeout=10.0)
            latency_ms = int((time.time() - start_t) * 1000)

            if resp.status_code == 200:
                try:
                    provider_model = resp.json().get("model")
                except (ValueError, AttributeError):
                    provider_model = None
                return {
                    "status": "LIVE_CONNECTED",
                    "connected": True,
                    "is_mock": False,
                    "model_id": provider_model,
                    "base_url": self.settings.META_API_BASE_URL,
                    "latency_ms": latency_ms,
                    "message": f"Successfully verified live Meta Model API connection ({latency_ms}ms).",
                }
            elif resp.status_code in (401, 403):
                return {
                    "status": "AUTHENTICATION_FAILED",
                    "connected": False,
                    "is_mock": False,
                    "model_id": self.settings.META_MODEL_ID,
                    "message": "Meta API rejected credentials (HTTP 401/403). Check MODEL_API_KEY validity.",
                }
            elif resp.status_code == 429:
                return {
                    "status": "RATE_LIMITED",
                    "connected": False,
                    "is_mock": False,
                    "model_id": self.settings.META_MODEL_ID,
                    "message": "Meta API rate limit exceeded (HTTP 429).",
                }
            else:
                return {
                    "status": "PROVIDER_UNAVAILABLE",
                    "connected": False,
                    "is_mock": False,
                    "model_id": self.settings.META_MODEL_ID,
                    "message": f"Meta API returned status {resp.status_code}.",
                }

        except MetaAPIError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return {
                "status": "PROVIDER_UNAVAILABLE",
                "connected": False,
                "is_mock": False,
                "model_id": self.settings.META_MODEL_ID,
                "message": f"Network error connecting to Meta API ({self.settings.META_API_BASE_URL}): {type(exc).__name__}",
            }
        except Exception as exc:
            return {
                "status": "PROVIDER_UNAVAILABLE",
                "connected": False,
                "is_mock": False,
                "model_id": self.settings.META_MODEL_ID,
                "message": f"Unexpected health check error: {type(exc).__name__}",
            }

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Send chat completion request to Meta API or return mock if explicitly in DEMO_MODE."""
        if self.settings.APP_MODE == "public_demo" and self.settings.LLM_PROVIDER != "meta" and not self.settings.ALLOW_DEV_PROVIDER:
            raise MetaAPIError("Development providers are disabled in public mode.", provider_status="PUBLIC_DEMO_DISABLED")
        if self.settings.APP_MODE == "public_demo" and not public_ai_is_ready(self.settings):
            raise MetaAPIError("Public demo is temporarily disabled.", provider_status="PUBLIC_DEMO_DISABLED")
        if self.settings.APP_MODE == "public_demo":
            max_tokens = min(max_tokens, self.settings.PUBLIC_MAX_TOKENS_PER_CALL)
        # 1. DEMO MODE — Explicitly allowed
        if self.settings.LLM_PROVIDER == "gemini":
            from .gemini_client import GeminiClient
            return await GeminiClient(self.settings, self.http_client).chat_completion(
                messages, temperature=temperature, max_tokens=max_tokens)
        if self.settings.LLM_PROVIDER == "replay":
            raise MetaAPIError("No replay cassette matches the selected provider and prompt.", provider_status="NOT_CONFIGURED")
        if self.settings.LLM_PROVIDER == "demo" or self.settings.DEMO_MODE:
            logger.info("Executing in DEMO_MODE: Returning explicitly labeled simulated output.")
            mock_data = await self._mock_completion(messages)
            mock_data["meta_integration"] = {
                "provider": "demo",
                "is_mock": True,
                "demo_mode": True,
                "model": None,
                "usage": None,
                "notice": "DEMO MODE — SIMULATED AI OUTPUT. Not called against live Meta API.",
            }
            return mock_data

        # 2. LIVE MODE — Must NEVER silently fallback to mock!
        api_key = self.settings.effective_api_key
        if not api_key:
            logger.error("LIVE MODE ERROR: MODEL_API_KEY is not configured.")
            raise MetaAPIError(
                "MODEL_API_KEY is not configured and DEMO_MODE is False. "
                "Configure a valid Meta API key in backend/.env or set DEMO_MODE=true for local simulation.",
                status_code=400,
                provider_status="NOT_CONFIGURED",
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PatchPilot/1.0",
        }

        url = f"{self.settings.META_API_BASE_URL.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.META_MODEL_ID,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        retries = self.settings.META_MAX_RETRIES
        delay = 1.0

        for attempt in range(1, retries + 1):
            try:
                start_t = time.time()
                if self.settings.APP_MODE == "public_demo":
                    self._reserve_public_call()
                resp = await self._post(url, headers=headers, json=payload,
                    timeout=httpx.Timeout(self.settings.META_API_TIMEOUT, connect=min(10.0, self.settings.META_API_TIMEOUT)))
                latency = round(time.time() - start_t, 3)

                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        content = data["choices"][0]["message"]["content"]
                        if not isinstance(content, str):
                            raise (ValueError("completion content is not text"))
                    except (ValueError, KeyError, IndexError, TypeError) as exc:
                        raise MetaAPIError("Meta API returned a malformed chat completion.", provider_status="PROVIDER_UNAVAILABLE") from exc
                    logger.info("Meta API request succeeded in %ss (attempt %d)", latency, attempt)
                    data["meta_integration"] = {
                        "provider": "meta_ai",
                        "is_mock": False,
                        "demo_mode": False,
                        "model": data.get("model"),
                        "request_id": data.get("id"),
                        "finish_reason": (data.get("choices") or [{}])[0].get("finish_reason"),
                        "base_url": self.settings.META_API_BASE_URL,
                        "latency_seconds": latency,
                        "request_status": resp.status_code,
                        "usage": data.get("usage"),
                    }
                    return data

                # 401/403: Do not retry authentication failures
                if resp.status_code in (401, 403):
                    logger.error("Meta API authentication failed (HTTP %d).", resp.status_code)
                    raise MetaAPIError(
                        f"Meta API authentication failed (HTTP {resp.status_code}). Verify MODEL_API_KEY.",
                        status_code=resp.status_code,
                        provider_status="AUTHENTICATION_FAILED",
                    )

                # 429: Rate limit
                if resp.status_code == 429:
                    if attempt < retries:
                        retry_after = resp.headers.get("Retry-After")
                        try:
                            wait = min(60.0, max(0.0, float(retry_after))) if retry_after else min(30.0, delay) * random.random()
                        except ValueError:
                            wait = min(30.0, delay) * random.random()
                        logger.warning("Meta API rate limited (429); retrying after provider backoff.")
                        await asyncio.sleep(wait)
                        delay *= 2
                        continue
                    raise MetaAPIError(
                        "Meta API rate limit exceeded after maximum retries.",
                        status_code=429,
                        provider_status="RATE_LIMITED",
                    )

                # 5xx: Server errors
                if (resp.status_code == 408 or resp.status_code >= 500) and attempt < retries:
                    wait = min(30.0, delay) * random.random()
                    logger.warning("Meta API transient HTTP error %d; retrying after backoff.", resp.status_code)
                    await asyncio.sleep(wait)
                    delay *= 2
                    continue

                raise MetaAPIError(
                    f"Meta API call failed with status {resp.status_code}.",
                    status_code=resp.status_code,
                    provider_status="PROVIDER_UNAVAILABLE",
                )

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < retries:
                    wait = min(30.0, delay) * random.random()
                    logger.warning("Meta API network failure (%s); retrying after backoff.", type(exc).__name__)
                    await asyncio.sleep(wait)
                    delay *= 2
                else:
                    raise MetaAPIError(
                        f"Meta API connection failed after {retries} retries: {type(exc).__name__}",
                        provider_status="PROVIDER_UNAVAILABLE",
                    )

        raise MetaAPIError("Meta API call failed unexpectedly.", provider_status="PROVIDER_UNAVAILABLE")

    async def _mock_completion(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Deterministic simulated generator strictly for DEMO_MODE."""
        await asyncio.sleep(0.3)
        full_prompt = "\n".join(message.get("content", "") for message in messages).lower()

        # Route by the requested artifact, using the system instructions too.
        if "test engineer" in full_prompt or "pytest test cases" in full_prompt or "regression test suite" in full_prompt:
            content = (
                "```python\n"
                "from core.calculator import compute_cumulative_total\n\n"
                "def test_cumulative_total_includes_final_item():\n"
                "    assert compute_cumulative_total([10.0, 20.0, 30.0]) == 60.0\n\n"
                "def test_cumulative_total_empty_input():\n"
                "    assert compute_cumulative_total([]) == 0.0\n"
                "```"
            )
        elif "edit block" in full_prompt or "exact-match" in full_prompt:
            content = json.dumps([
                {
                    "path": "core/calculator.py",
                    "old_text": "    for i in range(len(items) - 1):",
                    "new_text": "    for i in range(len(items)):"
                }
            ], indent=2)
        elif "unified diff" in full_prompt or "generate a clean" in full_prompt:
            content = (
                "```diff\n"
                "--- a/core/calculator.py\n"
                "+++ b/core/calculator.py\n"
                "@@ -16,3 +16,3 @@\n"
                "     total = 0.0\n"
                "-    for i in range(len(items) - 1):\n"
                "+    for i in range(len(items)):\n"
                "         total += items[i]\n"
                "```"
            )
        elif "structured repair plan" in full_prompt or "repair plan" in full_prompt or "root cause analysis" in full_prompt:
            plan_obj = {
                "problem_summary": "Off-by-one indexing boundary error in compute_cumulative_total terminates loop prematurely.",
                "root_cause": "The loop range(len(items) - 1) excludes the final element of the list from the accumulation summation.",
                "evidence": "Observed assertion failure in test_cumulative_total_inclusive: Expected 60.0 but got 30.0.",
                "candidate_files": ["core/calculator.py"],
                "proposed_changes": [
                    "Update loop termination condition to range(len(items))",
                    "Verify total accumulation encompasses all list items",
                ],
                "expected_behavior": "All items in the items list are accumulated into the cumulative sum.",
                "regression_test_plan": "Assert inclusive accumulation across multi-element lists and empty inputs.",
                "risks_and_assumptions": "Assumes items is an iterable of numeric values.",
            }
            content = json.dumps(plan_obj, indent=2)
        else:
            content = "DEMO MODE: no live provider call or test execution occurred; verification remains unavailable."

        return {
            "id": "chatcmpl-demo-simulated",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": None,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": None,
        }
