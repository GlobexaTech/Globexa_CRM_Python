"""Local inference configuration uses the real native HTTP contract without a key."""

import json

import httpx
import pytest

from app.services.ai.gateway import OllamaProvider
from app.services.crm.ai import build_gateway


@pytest.mark.parametrize("provider", ["ollama", "local"])
async def test_explicit_local_provider_uses_native_contract_without_key(monkeypatch, provider):
    monkeypatch.setenv("CRM_AI_PROVIDER", provider)
    monkeypatch.setenv("CRM_AI_MODEL", "explicit-local-model")
    monkeypatch.setenv("CRM_AI_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.delenv("CRM_AI_API_KEY", raising=False)
    gateway = build_gateway()
    assert gateway.routes[0].provider == "ollama"
    selected = gateway.providers["ollama"]
    assert isinstance(selected, OllamaProvider)
    calls = []

    async def transport(request):
        assert "authorization" not in request.headers
        calls.append((request.url.path, json.loads(request.content)))
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "message": {"content": '{"summary":"Verified","actions":[]}'},
                    "prompt_eval_count": 12,
                    "eval_count": 7,
                },
            )
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]], "prompt_eval_count": 3})

    await selected.client.aclose()
    selected.client = httpx.AsyncClient(
        base_url="http://127.0.0.1:11434/", transport=httpx.MockTransport(transport)
    )
    try:
        result = await selected.chat(
            "explicit-local-model",
            [{"role": "user", "content": "Review facts"}],
            temperature=0.1,
            max_tokens=2500,
            response_format={"type": "json_object"},
        )
        assert (result.input_tokens, result.output_tokens) == (12, 7)
        assert json.loads(result.content)["summary"] == "Verified"
        assert calls[0][1] == {
            "model": "explicit-local-model",
            "messages": [{"role": "user", "content": "Review facts"}],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 2500},
            "format": "json",
        }
        embedded = await selected.embed("embedding-model", ["Facts"])
        assert calls[1] == ("/api/embed", {"model": "embedding-model", "input": ["Facts"]})
        assert embedded.embeddings == [[0.1, 0.2]] and embedded.input_tokens == 3
        assert embedded.output_tokens is None
    finally:
        await selected.client.aclose()


@pytest.mark.parametrize("missing", ["CRM_AI_PROVIDER", "CRM_AI_MODEL", "CRM_AI_BASE_URL"])
def test_local_provider_still_requires_explicit_configuration(monkeypatch, missing):
    monkeypatch.setenv("CRM_AI_PROVIDER", "ollama")
    monkeypatch.setenv("CRM_AI_MODEL", "explicit-local-model")
    monkeypatch.setenv("CRM_AI_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.delenv("CRM_AI_API_KEY", raising=False)
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(RuntimeError, match="ai_not_configured"):
        build_gateway()


def test_cloud_provider_still_requires_secret(monkeypatch):
    monkeypatch.setenv("CRM_AI_PROVIDER", "openai")
    monkeypatch.setenv("CRM_AI_MODEL", "explicit-cloud-model")
    monkeypatch.setenv("CRM_AI_BASE_URL", "https://provider.example/v1")
    monkeypatch.delenv("CRM_AI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ai_not_configured"):
        build_gateway()
