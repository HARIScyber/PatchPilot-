"""Gemini adapter tests use mocked responses only; no live API calls."""
import pytest
import httpx

from app.core.config import Settings
from app.services.gemini_client import GeminiClient
from app.services.meta_client import MetaAPIError, MetaClient


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {
            "responseId": "r-1", "modelVersion": "gemini-from-response",
            "candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"totalTokenCount": 3},
        }
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeHTTP:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def make_settings(**overrides):
    values = {"APP_MODE": "local", "LLM_PROVIDER": "gemini",
              "GEMINI_API_KEY": "test-gemini-secret", "GEMINI_MODEL_ID": "test-model",
              "META_MAX_RETRIES": 1}
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_gemini_maps_roles_uses_header_schema_and_response_model():
    http = FakeHTTP(FakeResponse())
    client = GeminiClient(make_settings(), http)
    result = await client.chat_completion([
        {"role": "system", "content": "be concise"},
        {"role": "user", "content": "hello"},
    ], response_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}})
    method, url, request = http.calls[0]
    assert method == "POST"
    assert url.endswith("/models/test-model:generateContent")
    assert request["headers"]["x-goog-api-key"] == "test-gemini-secret"
    assert "test-gemini-secret" not in url
    body = request["json"]
    assert body["systemInstruction"]["parts"][0]["text"] == "be concise"
    assert body["contents"][0]["role"] == "user"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert result["model"] == "gemini-from-response"
    assert result["meta_integration"]["provider"] == "gemini"
    assert result["usage"]["totalTokenCount"] == 3


@pytest.mark.asyncio
async def test_model_listing_uses_documented_endpoint_without_generation():
    http = FakeHTTP(FakeResponse(payload={"models": [{"name": "models/gemini-example",
                                                       "supportedGenerationMethods": ["generateContent"]}]}))
    models = await GeminiClient(make_settings(), http).list_models()
    method, url, request = http.calls[0]
    assert method == "GET"
    assert url.endswith("/models")
    assert request["headers"]["x-goog-api-key"] == "test-gemini-secret"
    assert models[0]["name"] == "models/gemini-example"


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "expected"), [(400, "MALFORMED_RESPONSE"),
                                                     (401, "AUTHENTICATION_FAILED"),
                                                     (403, "AUTHENTICATION_FAILED"),
                                                     (404, "MODEL_NOT_FOUND"),
                                                     (429, "RATE_LIMITED"),
                                                     (503, "PROVIDER_UNAVAILABLE")])
async def test_gemini_classifies_http_errors_without_exposing_body(status, expected):
    http = FakeHTTP(FakeResponse(status, {"error": {"message": "test-gemini-secret"}}))
    with pytest.raises(MetaAPIError) as error:
        await GeminiClient(make_settings(), http).chat_completion([{"role": "user", "content": "hi"}])
    assert error.value.provider_status == expected
    assert "test-gemini-secret" not in str(error.value)


@pytest.mark.asyncio
async def test_gemini_classifies_invalid_model_error_from_400():
    http = FakeHTTP(FakeResponse(400, {"error": {"message": "Invalid model name"}}))
    with pytest.raises(MetaAPIError) as error:
        await GeminiClient(make_settings(), http).chat_completion([{"role": "user", "content": "hi"}])
    assert error.value.provider_status == "MODEL_NOT_FOUND"


@pytest.mark.asyncio
async def test_gemini_retries_429_and_honors_retry_after(monkeypatch):
    http = FakeHTTP(FakeResponse(429, {"error": {"message": "rate limit"}}, {"Retry-After": "0"}), FakeResponse())
    waits = []

    async def no_wait(delay):
        waits.append(delay)

    monkeypatch.setattr("app.services.gemini_client.asyncio.sleep", no_wait)
    result = await GeminiClient(make_settings(META_MAX_RETRIES=2), http).chat_completion(
        [{"role": "user", "content": "retry"}])
    assert len(http.calls) == 2
    assert waits == [0.0]
    assert result["meta_integration"]["provider"] == "gemini"


@pytest.mark.asyncio
@pytest.mark.parametrize("first", [FakeResponse(503, {"error": {"message": "temporary"}}),
                                   httpx.ReadTimeout("timeout")])
async def test_gemini_retries_transient_server_and_timeout_failures(monkeypatch, first):
    class FirstFailureHTTP(FakeHTTP):
        async def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            if len(self.calls) == 1 and isinstance(first, Exception):
                raise first
            if len(self.calls) == 1:
                return first
            return FakeResponse()

    waits = []

    async def no_wait(delay):
        waits.append(delay)

    monkeypatch.setattr("app.services.gemini_client.asyncio.sleep", no_wait)
    http = FirstFailureHTTP()
    result = await GeminiClient(make_settings(META_MAX_RETRIES=2), http).chat_completion(
        [{"role": "user", "content": "retry"}])
    assert len(http.calls) == 2
    assert waits
    assert result["meta_integration"]["provider"] == "gemini"


@pytest.mark.asyncio
async def test_gemini_rejects_missing_candidate_as_malformed():
    http = FakeHTTP(FakeResponse(payload={"candidates": []}))
    with pytest.raises(MetaAPIError) as error:
        await GeminiClient(make_settings(), http).chat_completion([{"role": "user", "content": "hi"}])
    assert error.value.provider_status == "MALFORMED_RESPONSE"


@pytest.mark.asyncio
@pytest.mark.parametrize(("finish", "expected"), [("SAFETY", "RESPONSE_BLOCKED"),
                                                    ("MAX_TOKENS", "OUTPUT_TRUNCATED")])
async def test_gemini_surfaces_blocked_and_truncated_responses(finish, expected):
    http = FakeHTTP(FakeResponse(payload={"candidates": [{"content": {"parts": [{"text": "partial"}]},
                                                        "finishReason": finish}]}))
    with pytest.raises(MetaAPIError) as error:
        await GeminiClient(make_settings(), http).chat_completion([{"role": "user", "content": "hi"}])
    assert error.value.provider_status == expected


@pytest.mark.asyncio
async def test_selected_gemini_failure_never_calls_meta():
    http = FakeHTTP(FakeResponse(status_code=401, payload={"error": {"message": "bad key"}}))
    client = MetaClient(settings=make_settings(), http_client=http)
    with pytest.raises(MetaAPIError) as error:
        await client.chat_completion([{"role": "user", "content": "hello"}])
    assert error.value.provider_status == "AUTHENTICATION_FAILED"
    assert len(http.calls) == 1
    assert "generativelanguage.googleapis.com" in http.calls[0][1]


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        Settings(_env_file=None, LLM_PROVIDER="automatic-fallback")


def test_provider_secrets_are_redacted_from_settings_repr():
    settings = make_settings()
    assert "test-gemini-secret" not in repr(settings)
    assert "test-gemini-secret" not in str(settings.safe_dict())
    assert "***redacted***" in str(settings.safe_dict())
