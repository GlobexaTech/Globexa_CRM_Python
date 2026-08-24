"""
Celery tasks for AI operations.
"""
from celery import shared_task
import structlog
from typing import Optional, List, Dict, Any

logger = structlog.get_logger()


class AIProvider:
    """Base AI provider interface."""
    async def complete(self, prompt: str, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError


class OllamaProvider(AIProvider):
    """Local Ollama provider."""
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2:3b"):
        self.base_url = base_url
        self.model = model

    async def complete(self, prompt: str, **kwargs) -> Dict[str, Any]:
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False, **kwargs}
            )
            response.raise_for_status()
            data = response.json()
            return {
                "content": data.get("response", ""),
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            }


class NVIDIAProvider(AIProvider):
    """NVIDIA NIM provider (OpenAI-compatible)."""
    def __init__(self, api_key: str, base_url: str = "https://integrate.api.nvidia.com/v1", model: str = "nvidia/nemotron-3-ultra"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def complete(self, prompt: str, **kwargs) -> Dict[str, Any]:
        import httpx
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": self.model, "messages": [{"role": "user", "content": prompt}], **kwargs}
            )
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})
            return {
                "content": choice["message"]["content"],
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }


class AIRouter:
    """AI Router - routes tasks to local or cloud providers based on task type."""

    LOCAL_TASKS = {
        "classification", "simple_scoring", "extraction", "summarization",
        "intent_identification", "tagging", "routing_decision",
    }

    def __init__(self, ollama_base_url: str, ollama_model: str, nvidia_api_key: str, nvidia_model: str):
        self.local_provider = OllamaProvider(ollama_base_url, ollama_model)
        self.cloud_provider = NVIDIAProvider(nvidia_api_key, model=nvidia_model)

    def should_use_local(self, task_type: str) -> bool:
        """Determine if task should use local model."""
        return task_type in self.LOCAL_TASKS

    async def route(self, task_type: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Route task to appropriate provider and return result with metadata."""
        use_local = self.should_use_local(task_type)
        provider = self.local_provider if use_local else self.cloud_provider
        provider_name = "ollama" if use_local else "nvidia"

        import time
        start = time.time()
        try:
            result = await provider.complete(prompt, **kwargs)
            latency_ms = int((time.time() - start) * 1000)
            result.update({
                "provider": provider_name,
                "latency_ms": latency_ms,
                "success": True,
            })
        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            result = {
                "content": "",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "provider": provider_name,
                "latency_ms": latency_ms,
                "success": False,
                "error_message": str(e),
            }
        return result


# Global router instance (initialized in tasks)
_router: Optional[AIRouter] = None


def get_router() -> AIRouter:
    """Get or create AI router instance."""
    global _router
    if _router is None:
        from app.core.config import get_settings
        settings = get_settings()
        _router = AIRouter(
            ollama_base_url=settings.ai_router.local.base_url,
            ollama_model=settings.ai_router.local.default_model,
            nvidia_api_key=settings.ai_router.cloud.providers.get("nvidia", {}).get("api_key", "") or "",
            nvidia_model=settings.ai_router.cloud.providers.get("nvidia", {}).get("default_model", "nvidia/nemotron-3-ultra"),
        )
    return _router


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_classify_task(self, tenant_id: str, user_id: str, task_type: str, prompt: str, correlation_id: str = None):
    """Run AI classification task (local preferred)."""
    logger.info("AI classify task", tenant_id=tenant_id, task_type=task_type)
    router = get_router()
    import asyncio
    result = asyncio.run(router.route(task_type, prompt))
    # TODO: Log to ai_usage_logs table
    return result


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_score_lead_task(self, tenant_id: str, user_id: str, lead_data: dict, correlation_id: str = None):
    """Score a lead using AI."""
    logger.info("AI score lead task", tenant_id=tenant_id)
    # Build scoring prompt
    prompt = f"""
    Analyze this lead and provide a score (0-100) with reasoning:
    Lead: {lead_data}
    
    Consider: company size, industry fit, engagement signals, budget indicators, authority.
    Return JSON: {{"score": 85, "reasoning": "...", "factors": ["...", "..."]}}
    """
    router = get_router()
    import asyncio
    result = asyncio.run(router.route("lead_scoring", prompt))
    return result


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_generate_email_task(self, tenant_id: str, user_id: str, context: dict, correlation_id: str = None):
    """Generate personalized email using AI."""
    logger.info("AI generate email task", tenant_id=tenant_id)
    prompt = f"""
    Write a personalized sales email for:
    {context}
    
    Tone: professional, concise, value-focused.
    Return JSON: {{"subject": "...", "body": "..."}}
    """
    router = get_router()
    import asyncio
    result = asyncio.run(router.route("personalization", prompt))
    return result


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_analyze_reply_task(self, tenant_id: str, user_id: str, reply_text: str, context: dict, correlation_id: str = None):
    """Analyze inbound reply for intent and sentiment."""
    logger.info("AI analyze reply task", tenant_id=tenant_id)
    prompt = f"""
    Analyze this email reply:
    Reply: {reply_text}
    Context: {context}
    
    Return JSON: {{
        "intent": "interested|needs_info|pricing_objection|not_interested|out_of_office|wrong_person|unsubscribe|meeting_request|support|spam|unknown",
        "sentiment": "positive|neutral|negative",
        "purchase_probability": "high|medium|low",
        "questions": ["..."],
        "recommended_action": "...",
        "confidence": 0.92
    }}
    """
    router = get_router()
    import asyncio
    result = asyncio.run(router.route("reply_analysis", prompt))
    return result


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_next_best_action_task(self, tenant_id: str, user_id: str, lead_data: dict, correlation_id: str = None):
    """Recommend next best action for a lead."""
    logger.info("AI next best action task", tenant_id=tenant_id)
    prompt = f"""
    Recommend next best action for this lead:
    {lead_data}
    
    Return JSON: {{
        "action": "call|email|whatsapp|schedule_demo|send_proposal|nurture|wait|disqualify|escalate",
        "reasoning": "...",
        "confidence": 0.89,
        "timeline": "within_2_hours|today|this_week|next_week"
    }}
    """
    router = get_router()
    import asyncio
    result = asyncio.run(router.route("next_best_action", prompt))
    return result


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_generate_proposal_task(self, tenant_id: str, user_id: str, proposal_data: dict, correlation_id: str = None):
    """Generate a sales proposal."""
    logger.info("AI generate proposal task", tenant_id=tenant_id)
    prompt = f"""
    Generate a professional sales proposal:
    {proposal_data}
    
    Return JSON: {{
        "title": "...",
        "executive_summary": "...",
        "solution_overview": "...",
        "pricing": [...],
        "terms": "...",
        "next_steps": "..."
    }}
    """
    router = get_router()
    import asyncio
    result = asyncio.run(router.route("proposal_generation", prompt))
    return result


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_lead_miner_task(self, tenant_id: str, user_id: str, icp_criteria: dict, correlation_id: str = None):
    """Run AI Lead Miner to find prospects."""
    logger.info("AI lead miner task", tenant_id=tenant_id)
    prompt = f"""
    Find companies matching this ICP:
    {icp_criteria}
    
    Return JSON: {{
        "companies": [
            {{"name": "...", "website": "...", "founder": "...", "linkedin": "...", "email": "...", "location": "...", "size": "...", "score": 85, "reason": "..."}}
        ]
    }}
    """
    router = get_router()
    import asyncio
    result = asyncio.run(router.route("lead_mining", prompt))
    return result


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_chat_assistant_task(self, tenant_id: str, user_id: str, message: str, context: dict, correlation_id: str = None):
    """Handle AI chat assistant request with tool calling."""
    logger.info("AI chat assistant task", tenant_id=tenant_id)
    # This would use a more sophisticated agent with tool calling
    prompt = f"""
    You are Globexa AI Assistant. Help the user with CRM tasks.
    User message: {message}
    Context: {context}
    
    Available tools: search_leads, get_lead, create_campaign, assign_lead, schedule_followup, send_email, create_proposal, update_stage
    
    Respond with tool calls or direct answer.
    """
    router = get_router()
    import asyncio
    result = asyncio.run(router.route("chat_assistant", prompt))
    return result