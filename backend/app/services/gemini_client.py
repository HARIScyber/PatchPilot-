"""Native Gemini REST adapter. It never logs request data or provider error bodies."""
from __future__ import annotations

import asyncio
from email.utils import parsedate_to_datetime
import json
import logging
import random
import time
from typing import Any

import httpx

from ..core.config import Settings, get_settings
from .meta_client import MetaAPIError, get_shared_http_client

logger = logging.getLogger("patchpilot.services.gemini_client")


class GeminiClient:
    def __init__(self, settings: Settings | None = None, http_client=None):
        self.settings = settings or get_settings()
        self.http_client = http_client

    @property
    def api_key(self) -> str:
        return self.settings.GEMINI_API_KEY.get_secret_value()

    async def _request(self, method: str, url: str, **kwargs):
        client = self.http_client or get_shared_http_client()
        if client is not None:
            return await client.request(method, url, **kwargs)
        async with httpx.AsyncClient(timeout=kwargs.pop("timeout", 30.0)) as client:
            return await client.request(method, url, **kwargs)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise MetaAPIError("GEMINI_API_KEY is not configured.", provider_status="NOT_CONFIGURED")
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def _classify_error(self, status: int, payload: dict[str, Any] | None = None) -> MetaAPIError:
        message = "Gemini provider request failed."
        code = "PROVIDER_UNAVAILABLE"
        if status in (401, 403):
            message, code = "Gemini authentication failed.", "AUTHENTICATION_FAILED"
        elif status == 404:
            message, code = "Gemini model was not found; check GEMINI_MODEL_ID.", "MODEL_NOT_FOUND"
        elif status == 429:
            message, code = "Gemini rate limit or quota was reached.", "RATE_LIMITED"
            error = (payload or {}).get("error", {})
            details = json.dumps(error).lower() if isinstance(error, dict) else ""
            if "quota" in details or "billing" in details or "resource_exhausted" in details:
                code = "QUOTA_EXHAUSTED"
        elif status == 400:
            details = json.dumps((payload or {}).get("error", {})).lower()
            if "model" in details and any(term in details for term in ("not found", "invalid", "unsupported")):
                message, code = "Gemini model was rejected; check GEMINI_MODEL_ID.", "MODEL_NOT_FOUND"
            else:
                message, code = "Gemini rejected the request (HTTP 400).", "MALFORMED_RESPONSE"
        elif status < 500 and status != 408:
            message = f"Gemini rejected the request (HTTP {status})."
            code = "MALFORMED_RESPONSE"
        return MetaAPIError(message, status_code=status, provider_status=code)

    async def list_models(self) -> list[dict[str, Any]]:
        if not self.api_key:
            raise MetaAPIError("GEMINI_API_KEY is not configured.", provider_status="NOT_CONFIGURED")
        url = f"{self.settings.GEMINI_API_BASE_URL.rstrip('/')}/models"
        response = await self._request("GET", url, headers=self._headers(), timeout=20.0)
        if response.status_code != 200:
            try:
                payload = response.json()
            except (ValueError, AttributeError):
                payload = None
            raise self._classify_error(response.status_code, payload)
        try:
            models = response.json().get("models", [])
            return [{"name": item.get("name"), "supported_generation_methods": item.get("supportedGenerationMethods", [])}
                    for item in models if isinstance(item, dict)]
        except (ValueError, AttributeError, TypeError) as exc:
            raise MetaAPIError("Gemini model listing returned malformed data.", provider_status="MALFORMED_RESPONSE") from exc

    async def check_provider_health(self) -> dict[str, Any]:
        if not self.api_key:
            return {"status": "NOT_CONFIGURED", "connected": False, "provider": "gemini",
                    "model_id": None, "message": "GEMINI_API_KEY is not configured."}
        if not self.settings.GEMINI_MODEL_ID.strip():
            return {"status": "NOT_CONFIGURED", "connected": False, "provider": "gemini",
                    "model_id": None, "message": "GEMINI_MODEL_ID is not configured."}
        started = time.perf_counter()
        try:
            result = await self.chat_completion([{"role": "user", "content": "Reply with OK."}], max_tokens=8)
            model = result.get("model")
            if not model:
                raise MetaAPIError("Gemini response did not identify the serving model.", provider_status="MALFORMED_RESPONSE")
            return {"status": "LIVE_CONNECTED", "connected": True, "provider": "gemini",
                    "model_id": model, "latency_ms": int((time.perf_counter() - started) * 1000),
                    "message": "Gemini test request succeeded."}
        except MetaAPIError as exc:
            return {"status": exc.provider_status, "connected": False, "provider": "gemini",
                    "model_id": self.settings.GEMINI_MODEL_ID, "message": str(exc)}
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return {"status": "PROVIDER_UNAVAILABLE", "connected": False, "provider": "gemini",
                    "model_id": self.settings.GEMINI_MODEL_ID, "message": f"Gemini connection failed ({type(exc).__name__})."}

    async def chat_completion(self, messages: list[dict[str, str]], *, temperature: float = 0.2,
                              max_tokens: int = 4096, response_schema: dict | None = None) -> dict[str, Any]:
        if not self.settings.GEMINI_MODEL_ID.strip():
            raise MetaAPIError("GEMINI_MODEL_ID is not configured.", provider_status="NOT_CONFIGURED")
        system_parts = []
        contents = []
        for message in messages:
            role = message.get("role", "user")
            text = str(message.get("content", ""))
            if role == "system":
                system_parts.append({"text": text})
            else:
                contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": text}]})
        payload: dict[str, Any] = {"contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}
        if response_schema:
            payload["generationConfig"].update({"responseMimeType": "application/json", "responseSchema": response_schema})
        url = (f"{self.settings.GEMINI_API_BASE_URL.rstrip('/')}/models/"
               f"{self.settings.GEMINI_MODEL_ID}:generateContent")
        retries = max(1, self.settings.META_MAX_RETRIES)
        delay = 1.0
        for attempt in range(retries):
            started = time.perf_counter()
            try:
                response = await self._request("POST", url, headers=self._headers(), json=payload,
                    timeout=httpx.Timeout(self.settings.META_API_TIMEOUT, connect=min(10.0, self.settings.META_API_TIMEOUT)))
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt + 1 < retries:
                    await asyncio.sleep(random.uniform(0, min(delay, 30)))
                    delay *= 2
                    continue
                raise MetaAPIError(f"Gemini connection failed ({type(exc).__name__}).", provider_status="PROVIDER_UNAVAILABLE") from None
            if response.status_code != 200:
                try:
                    error_payload = response.json()
                except (ValueError, AttributeError):
                    error_payload = None
                if response.status_code in (408, 429) or response.status_code >= 500:
                    if attempt + 1 < retries:
                        retry_after = response.headers.get("Retry-After")
                        try:
                            wait = min(60.0, max(0.0, float(retry_after))) if retry_after else random.uniform(0, min(delay, 30))
                        except ValueError:
                            try:
                                wait = min(60.0, max(0.0, (parsedate_to_datetime(retry_after).timestamp() - time.time())))
                            except (TypeError, ValueError, OverflowError):
                                wait = random.uniform(0, min(delay, 30))
                        await asyncio.sleep(wait)
                        delay *= 2
                        continue
                raise self._classify_error(response.status_code, error_payload)
            try:
                data = response.json()
                candidate = data["candidates"][0]
                finish_reason = candidate.get("finishReason")
                if finish_reason in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"}:
                    raise MetaAPIError(f"Gemini blocked the response ({finish_reason}).", provider_status="RESPONSE_BLOCKED")
                if finish_reason == "MAX_TOKENS":
                    raise MetaAPIError("Gemini output was truncated at the token limit.", provider_status="OUTPUT_TRUNCATED")
                text = "".join(part.get("text", "") for part in candidate["content"]["parts"] if isinstance(part, dict))
                if not text:
                    raise ValueError("empty candidate text")
            except MetaAPIError:
                raise
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise MetaAPIError("Gemini returned a malformed completion.", provider_status="MALFORMED_RESPONSE") from exc
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {"id": data.get("responseId"), "model": data.get("modelVersion"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                             "finish_reason": finish_reason}],
                "usage": data.get("usageMetadata"),
                "meta_integration": {"provider": "gemini", "is_mock": False, "model": data.get("modelVersion"),
                                     "request_id": data.get("responseId"),
                                     "usage": data.get("usageMetadata"), "latency_ms": latency_ms,
                                     "finish_reason": finish_reason}}
        raise MetaAPIError("Gemini request failed.", provider_status="PROVIDER_UNAVAILABLE")
