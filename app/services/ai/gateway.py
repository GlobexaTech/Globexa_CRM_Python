"""Provider-neutral AI foundation with explicit routing, fallback and usage ledger."""
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
import httpx
from app.models import AIProviderEnum, AIUsageLog


@dataclass
class Generation:
    content: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    embeddings: list | None = None
    provider: str = ""
    model: str = ""
    latency_ms: int = 0
    tool_calls: list | None = None


class Provider(Protocol):
    async def generate(self, model: str, prompt: str, **kwargs) -> Generation: ...
    async def chat(self, model: str, messages: list, **kwargs) -> Generation: ...
    async def embed(self, model: str, texts: list[str], **kwargs) -> Generation: ...


class CompatibleProvider:
    """OpenAI, DeepSeek, NVIDIA NIM and local OpenAI-compatible endpoints."""
    def __init__(self, base_url, api_key, client=None):
        self.client = client or httpx.AsyncClient(base_url=base_url.rstrip("/") + "/",
                                                headers={"Authorization": f"Bearer {api_key}"},
                                                timeout=60)

    async def generate(self, model, prompt, **kwargs):
        return await self.chat(model, [{"role": "user", "content": prompt}], **kwargs)

    async def chat(self, model, messages, **kwargs):
        response = await self.client.post("chat/completions", json={
            "model": model, "messages": messages, **kwargs})
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage", {})
        return Generation(data["choices"][0]["message"].get("content") or "",
                          usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))

    async def embed(self, model, texts, **kwargs):
        response = await self.client.post("embeddings", json={"model": model, "input": texts, **kwargs})
        response.raise_for_status()
        data = response.json()
        return Generation(input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                          embeddings=[entry["embedding"] for entry in data["data"]])


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model: str
    input_cost_per_million: Decimal | None = None
    output_cost_per_million: Decimal | None = None


class AIGateway:
    def __init__(self, providers: dict[str, Provider], routes: list[ModelRoute]):
        if not routes:
            raise ValueError("At least one model route is required")
        for route in routes:
            AIProviderEnum(route.provider)
            if route.provider not in providers:
                raise ValueError("Model provider is unavailable")
        self.providers, self.routes = providers, routes

    async def execute(self, db, tenant_id, user_id, task, operation, **kwargs):
        if operation not in {"generate", "chat", "embed"}:
            raise ValueError("Unknown AI operation")
        if db is None:
            raise ValueError("AI execution requires a usage ledger transaction")
        for route in self.routes:
            start = time.monotonic()
            result = None
            error = None
            try:
                result = await getattr(self.providers[route.provider], operation)(route.model, **kwargs)
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                error = type(exc).__name__
            cost = None
            if result and route.input_cost_per_million is not None and route.output_cost_per_million is not None:
                cost = (result.input_tokens * route.input_cost_per_million +
                        result.output_tokens * route.output_cost_per_million) / 1_000_000
            usage = AIUsageLog(tenant_id=tenant_id, user_id=user_id, task_type=task,
                              provider=AIProviderEnum(route.provider), model=route.model,
                              input_tokens=result.input_tokens if result else 0,
                              output_tokens=result.output_tokens if result else 0,
                              total_tokens=result.input_tokens + result.output_tokens if result else 0,
                              latency_ms=int((time.monotonic()-start)*1000),
                              estimated_cost_usd=cost, success=result is not None, error_message=error)
            # External usage already happened. Its ledger must survive a CRM rollback.
            from app.core.tenant_context import tenant_db_context
            async with tenant_db_context(tenant_id, user_id) as ledger_db:
                ledger_db.add(usage)
            if result:
                result.provider = route.provider
                result.model = route.model
                result.latency_ms = int((time.monotonic()-start)*1000)
                return result
        raise RuntimeError("All configured AI providers failed")
