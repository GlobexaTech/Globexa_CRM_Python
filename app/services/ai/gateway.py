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
    input_tokens: int | None = None
    output_tokens: int | None = None
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
        self.client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )

    async def generate(self, model, prompt, **kwargs):
        return await self.chat(model, [{"role": "user", "content": prompt}], **kwargs)

    async def chat(self, model, messages, **kwargs):
        response = await self.client.post(
            "chat/completions", json={"model": model, "messages": messages, **kwargs}
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage", {})
        message = data["choices"][0]["message"]
        return Generation(
            message.get("content") or "",
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            tool_calls=message.get("tool_calls"),
        )

    async def embed(self, model, texts, **kwargs):
        response = await self.client.post(
            "embeddings", json={"model": model, "input": texts, **kwargs}
        )
        response.raise_for_status()
        data = response.json()
        return Generation(
            input_tokens=data.get("usage", {}).get("prompt_tokens"),
            embeddings=[entry["embedding"] for entry in data["data"]],
        )


class OllamaProvider:
    """Native local Ollama API, with no invented credential or usage values."""

    def __init__(self, base_url, client=None):
        self.client = client or httpx.AsyncClient(base_url=base_url.rstrip("/") + "/", timeout=60)

    async def generate(self, model, prompt, **kwargs):
        return await self.chat(model, [{"role": "user", "content": prompt}], **kwargs)

    async def chat(self, model, messages, **kwargs):
        options = {}
        if "temperature" in kwargs:
            options["temperature"] = kwargs.pop("temperature")
        if "max_tokens" in kwargs:
            options["num_predict"] = kwargs.pop("max_tokens")
        response_format = kwargs.pop("response_format", None)
        payload = {"model": model, "messages": messages, "stream": False, **kwargs}
        if options:
            payload["options"] = options
        if response_format:
            if response_format != {"type": "json_object"}:
                raise ValueError("Unsupported Ollama response format")
            payload["format"] = "json"
        response = await self.client.post("api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        return Generation(
            content=data["message"].get("content") or "",
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            tool_calls=data["message"].get("tool_calls"),
        )

    async def embed(self, model, texts, **kwargs):
        response = await self.client.post(
            "api/embed", json={"model": model, "input": texts, **kwargs}
        )
        response.raise_for_status()
        data = response.json()
        return Generation(input_tokens=data.get("prompt_eval_count"), embeddings=data["embeddings"])


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

    async def execute(
        self, db, tenant_id, user_id, task, operation, *, execution_id=None, automation_execution_id=None, automation_step_id=None, **kwargs
    ):
        if operation not in {"generate", "chat", "embed"}:
            raise ValueError("Unknown AI operation")
        if db is None:
            raise ValueError("AI execution requires a usage ledger transaction")
        retryable, retry_after = False, 0
        for route in self.routes:
            start = time.monotonic()
            result = None
            error = None
            try:
                result = await getattr(self.providers[route.provider], operation)(
                    route.model, **kwargs
                )
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                error = type(exc).__name__
                if isinstance(exc, httpx.HTTPStatusError):
                    status = exc.response.status_code
                    retryable = retryable or status in {429, 502, 503, 504}
                    header = exc.response.headers.get("Retry-After", "0")
                    if header.isdigit():
                        retry_after = max(retry_after, min(int(header), 3600))
                elif isinstance(exc, httpx.TransportError):
                    retryable = True
            cost = None
            if (
                result
                and result.input_tokens is not None
                and result.output_tokens is not None
                and route.input_cost_per_million is not None
                and route.output_cost_per_million is not None
            ):
                cost = (
                    result.input_tokens * route.input_cost_per_million
                    + result.output_tokens * route.output_cost_per_million
                ) / 1_000_000
            usage = AIUsageLog(
                tenant_id=tenant_id,
                user_id=user_id,
                task_type=task,
                provider=AIProviderEnum(route.provider),
                model=route.model,
                input_tokens=result.input_tokens if result else None,
                output_tokens=result.output_tokens if result else None,
                total_tokens=(
                    result.input_tokens + result.output_tokens
                    if result
                    and result.input_tokens is not None
                    and result.output_tokens is not None
                    else None
                ),
                execution_id=execution_id,
                automation_execution_id=automation_execution_id,
                automation_step_id=automation_step_id,
                correlation_id=str(execution_id) if execution_id else None,
                latency_ms=int((time.monotonic() - start) * 1000),
                estimated_cost_usd=cost,
                success=result is not None,
                error_message=error,
            )
            # External usage already happened. Its ledger must survive a CRM rollback.
            from app.core.tenant_context import tenant_db_context

            async with tenant_db_context(tenant_id, user_id) as ledger_db:
                ledger_db.add(usage)
            if result:
                result.provider = route.provider
                result.model = route.model
                result.latency_ms = int((time.monotonic() - start) * 1000)
                return result
        failure = RuntimeError("All configured AI providers failed")
        failure.retryable = retryable
        failure.retry_after = retry_after
        raise failure
