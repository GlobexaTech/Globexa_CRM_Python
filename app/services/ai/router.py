"""
AI Router service for Globexa CRM.
Provides unified interface for local and cloud AI providers with usage tracking.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, AsyncGenerator
from uuid import UUID, uuid4
import json
import time
import httpx
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.models import AIUsageLog, AIProviderEnum, AITaskTypeEnum, Tenant, User

logger = structlog.get_logger()
settings = get_settings()


@dataclass
class AIResponse:
    """Standardized AI response."""
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    provider: str = ""
    model: str = ""
    latency_ms: int = 0
    success: bool = True
    error_message: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        """Generate completion."""
        pass

    @abstractmethod
    async def stream_complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Stream completion."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier."""
        pass

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model name."""
        pass


class OllamaProvider(AIProvider):
    """Local Ollama provider for lightweight tasks."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2:3b"):
        self.base_url = base_url.rstrip("/")
        self._model = model
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def default_model(self) -> str:
        return self._model

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        return self._client

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        start = time.time()
        client = await self._get_client()

        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        if response_format and response_format.get("type") == "json_object":
            payload["format"] = "json"

        try:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

            message = data.get("message", {})
            content = message.get("content", "")

            # Ollama doesn't always return token counts in chat API
            prompt_eval = data.get("prompt_eval_count", 0)
            eval_count = data.get("eval_count", 0)

            return AIResponse(
                content=content,
                input_tokens=prompt_eval,
                output_tokens=eval_count,
                total_tokens=prompt_eval + eval_count,
                provider=self.provider_name,
                model=self._model,
                latency_ms=int((time.time() - start) * 1000),
                success=True,
            )
        except Exception as e:
            logger.error("Ollama completion failed", error=type(e).__name__)
            return AIResponse(
                content="",
                provider=self.provider_name,
                model=self._model,
                latency_ms=int((time.time() - start) * 1000),
                success=False,
                error_message=type(e).__name__,
            )

    async def stream_complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        client = await self._get_client()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip():
                    try:
                        data = json.loads(line)
                        chunk = data.get("message", {}).get("content", "")
                        if chunk:
                            yield chunk
                    except json.JSONDecodeError:
                        continue

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


class OpenAICompatibleProvider(AIProvider):
    """Base class for OpenAI-compatible APIs (NVIDIA NIM, OpenAI, etc.)."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        provider_name: str,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._model = model
        self._provider_name = provider_name
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def default_model(self) -> str:
        return self._model

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        start = time.time()
        client = await self._get_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if response_format:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        try:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

            choice = data["choices"][0]
            message = choice["message"]
            content = message.get("content", "")

            # Handle tool calls
            tool_calls = None
            if "tool_calls" in message:
                tool_calls = message["tool_calls"]

            usage = data.get("usage", {})

            return AIResponse(
                content=content,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                provider=self.provider_name,
                model=self._model,
                latency_ms=int((time.time() - start) * 1000),
                success=True,
                tool_calls=tool_calls,
            )
        except Exception as e:
            logger.error(f"{self.provider_name} completion failed", error=type(e).__name__)
            return AIResponse(
                content="",
                provider=self.provider_name,
                model=self._model,
                latency_ms=int((time.time() - start) * 1000),
                success=False,
                error_message=type(e).__name__,
            )

    async def stream_complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        client = await self._get_client()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {})
                        chunk = delta.get("content", "")
                        if chunk:
                            yield chunk
                    except json.JSONDecodeError:
                        continue

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


class NVIDIAProvider(OpenAICompatibleProvider):
    """NVIDIA NIM provider."""
    def __init__(self, api_key: str, base_url: str = "https://integrate.api.nvidia.com/v1", model: str = "nvidia/nemotron-3-ultra"):
        super().__init__(api_key, base_url, model, "nvidia")


class OpenAIProvider(OpenAICompatibleProvider):
    """OpenAI provider."""
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "gpt-4o-mini"):
        super().__init__(api_key, base_url, model, "openai")


class AnthropicProvider(AIProvider):
    """Anthropic Claude provider (not OpenAI-compatible)."""
    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com/v1", model: str = "claude-3-5-haiku-20241022"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._model = model
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def default_model(self) -> str:
        return self._model

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0),
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
            )
        return self._client

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        start = time.time()
        client = await self._get_client()

        messages = [{"role": "user", "content": prompt}]

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if tools:
            # Convert to Anthropic tool format
            payload["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "input_schema": t["function"].get("parameters", {}),
                }
                for t in tools
            ]

        try:
            response = await client.post(f"{self.base_url}/messages", json=payload)
            response.raise_for_status()
            data = response.json()

            content = ""
            tool_calls = None
            for block in data.get("content", []):
                if block["type"] == "text":
                    content += block["text"]
                elif block["type"] == "tool_use":
                    if tool_calls is None:
                        tool_calls = []
                    tool_calls.append({
                        "id": block["id"],
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(block["input"]),
                        },
                    })

            usage = data.get("usage", {})

            return AIResponse(
                content=content,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                provider=self.provider_name,
                model=self._model,
                latency_ms=int((time.time() - start) * 1000),
                success=True,
                tool_calls=tool_calls,
            )
        except Exception as e:
            logger.error("Anthropic completion failed", error=type(e).__name__)
            return AIResponse(
                content="",
                provider=self.provider_name,
                model=self._model,
                latency_ms=int((time.time() - start) * 1000),
                success=False,
                error_message=type(e).__name__,
            )

    async def stream_complete(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        # Streaming implementation for Anthropic
        yield "Not implemented yet"

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


class AIRouter:
    """
    AI Router - routes tasks to appropriate provider based on task type.
    Implements the blueprint's local-first, cloud-fallback architecture.
    """

    # Tasks suitable for local models (per blueprint)
    LOCAL_TASKS = {
        AITaskTypeEnum.CLASSIFICATION,
        AITaskTypeEnum.SIMPLE_SCORING,
        AITaskTypeEnum.EXTRACTION,
        AITaskTypeEnum.SUMMARIZATION,
        AITaskTypeEnum.INTENT_IDENTIFICATION,
        AITaskTypeEnum.TAGGING,
        AITaskTypeEnum.ROUTING_DECISION,
    }

    def __init__(self):
        self._local_provider: Optional[OllamaProvider] = None
        self._cloud_providers: Dict[str, AIProvider] = {}
        self._initialized = False

    def initialize(self):
        """Initialize providers from settings."""
        if self._initialized:
            return

        # Local provider (Ollama)
        if settings.ai_router.local.enabled:
            self._local_provider = OllamaProvider(
                base_url=settings.ai_router.local.base_url,
                model=settings.ai_router.local.default_model,
            )

        # Cloud providers
        cloud_config = settings.ai_router.cloud
        for provider_name, config in cloud_config.providers.items():
            if not config.enabled:
                continue

            api_key = config.get_api_key()
            if not api_key:
                logger.warning(f"Cloud provider {provider_name} enabled but no API key found")
                continue

            if provider_name == "nvidia":
                self._cloud_providers[provider_name] = NVIDIAProvider(
                    api_key=api_key,
                    base_url=config.base_url,
                    model=config.default_model,
                )
            elif provider_name == "deepseek":
                self._cloud_providers[provider_name] = OpenAICompatibleProvider(
                    api_key=api_key, base_url=config.base_url, model=config.default_model, provider_name="deepseek")
            elif provider_name == "openai":
                self._cloud_providers[provider_name] = OpenAIProvider(
                    api_key=api_key,
                    base_url=config.base_url,
                    model=config.default_model,
                )
            elif provider_name == "anthropic":
                self._cloud_providers[provider_name] = AnthropicProvider(
                    api_key=api_key,
                    base_url=config.base_url,
                    model=config.default_model,
                )

        self._initialized = True
        logger.info("AI Router initialized", local=bool(self._local_provider), cloud=list(self._cloud_providers.keys()))

    def should_use_local(self, task_type: AITaskTypeEnum) -> bool:
        """Determine if task should use local model."""
        return task_type in self.LOCAL_TASKS and self._local_provider is not None

    def get_provider(self, task_type: AITaskTypeEnum) -> AIProvider:
        """Get the appropriate provider for a task type."""
        self.initialize()

        if self.should_use_local(task_type):
            return self._local_provider

        # Use default cloud provider
        default_provider_name = settings.ai_router.cloud.default_provider
        provider = self._cloud_providers.get(default_provider_name)
        if not provider:
            # Fallback to any available cloud provider
            provider = next(iter(self._cloud_providers.values()), None)

        if not provider:
            raise RuntimeError("No AI provider available")

        return provider

    async def complete(
        self,
        task_type: AITaskTypeEnum,
        prompt: str,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        correlation_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> AIResponse:
        """
        Execute AI completion with automatic provider routing and usage logging.
        """
        from app.services.ai.gateway import AIGateway, ModelRoute, Generation
        first = self.get_provider(task_type)
        ordered = [first] + [p for p in self._cloud_providers.values() if p is not first]
        class Adapter:
            def __init__(self, provider):
                self.provider = provider
            async def generate(self, model, **kwargs):
                response = await self.provider.complete(**kwargs)
                if not response.success:
                    raise RuntimeError("Provider failed")
                return Generation(response.content, response.input_tokens, response.output_tokens,
                                  tool_calls=response.tool_calls)
        gateway = AIGateway({p.provider_name: Adapter(p) for p in ordered},
                            [ModelRoute(p.provider_name, p.default_model) for p in ordered])
        result = await gateway.execute(db, tenant_id, user_id, task_type, "generate",
            prompt=prompt, system_prompt=system_prompt, temperature=temperature,
            max_tokens=max_tokens, response_format=response_format, tools=tools, tool_choice=tool_choice)
        return AIResponse(content=result.content, input_tokens=result.input_tokens,
                          output_tokens=result.output_tokens, total_tokens=result.input_tokens+result.output_tokens,
                          provider=result.provider, model=result.model, latency_ms=result.latency_ms,
                          tool_calls=result.tool_calls)

    async def close(self):
        """Close all provider connections."""
        if self._local_provider:
            await self._local_provider.close()
        for provider in self._cloud_providers.values():
            await provider.close()


# Global router instance
_router: Optional[AIRouter] = None


def get_ai_router() -> AIRouter:
    """Get or create global AI router instance."""
    global _router
    if _router is None:
        _router = AIRouter()
    return _router