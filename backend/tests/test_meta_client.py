"""Deterministic tests for the Meta Model API adapter (no live credentials used)."""
import asyncio

import pytest

from app.core.config import Settings
from app.services.meta_client import MetaAPIError, MetaClient


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {"id": "call-1", "model": "muse-spark-1.3", "choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 2}}
        self.text = text

    def json(self):
        return self._payload


class FakeAsyncClient:
    response = FakeResponse()
    requests = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, headers, json):
        self.requests.append((url, headers, json))
        return self.response


@pytest.fixture
def client(monkeypatch):
    FakeAsyncClient.requests = []
    monkeypatch.setattr("app.services.meta_client.httpx.AsyncClient", FakeAsyncClient)
    instance = MetaClient()
    instance.settings = Settings(MODEL_API_KEY="test-secret", DEMO_MODE=False, META_MAX_RETRIES=1)
    return instance


@pytest.mark.asyncio
async def test_live_request_uses_official_endpoint_model_and_bearer(client):
    result = await client.chat_completion([{"role": "user", "content": "hello"}])
    url, headers, payload = FakeAsyncClient.requests[0]
    assert url == "https://api.meta.ai/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-secret"
    assert payload["model"] == "muse-spark-1.3"
    assert result["meta_integration"]["provider"] == "meta_ai"
    assert result["meta_integration"]["usage"]["total_tokens"] == 2


@pytest.mark.asyncio
async def test_live_mode_without_credentials_never_falls_back(client):
    client.settings = Settings(DEMO_MODE=False, META_MAX_RETRIES=1)
    with pytest.raises(MetaAPIError) as error:
        await client.chat_completion([{"role": "user", "content": "hello"}])
    assert error.value.provider_status == "NOT_CONFIGURED"
    assert FakeAsyncClient.requests == []


@pytest.mark.asyncio
async def test_malformed_success_response_is_rejected(client):
    FakeAsyncClient.response = FakeResponse(payload={"choices": []})
    with pytest.raises(MetaAPIError, match="malformed"):
        await client.chat_completion([{"role": "user", "content": "hello"}])


@pytest.mark.asyncio
async def test_auth_error_does_not_expose_key_or_provider_body(client):
    FakeAsyncClient.response = FakeResponse(status_code=401, text="test-secret")
    with pytest.raises(MetaAPIError) as error:
        await client.chat_completion([{"role": "user", "content": "hello"}])
    assert "test-secret" not in str(error.value)
    assert error.value.response_body is None
    assert error.value.provider_status == "AUTHENTICATION_FAILED"
