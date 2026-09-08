"""
Celery tasks for AI operations using the new AI Router service.
"""
from celery import shared_task
import structlog
from typing import Dict, Any, Optional
from uuid import UUID

logger = structlog.get_logger()


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_classify_task(self, tenant_id: str, user_id: str, task_type: str, prompt: str, correlation_id: str = None):
    """Run AI classification task (local preferred)."""
    logger.info("AI classify task", tenant_id=tenant_id, task_type=task_type)
    from app.services.ai.router import get_ai_router
    from app.core.tenant_context import tenant_db_context
    import asyncio

    async def _run():
        router = get_ai_router()
        async with tenant_db_context(tenant_id) as db:
            result = await router.complete(
                task_type=task_type,
                prompt=prompt,
                tenant_id=UUID(tenant_id),
                user_id=UUID(user_id) if user_id else None,
                correlation_id=correlation_id,
                db=db,
            )
            await db.commit()
            return result

    result = asyncio.run(_run())
    return {
        "content": result.content,
        "provider": result.provider,
        "model": result.model,
        "tokens": result.total_tokens,
        "latency_ms": result.latency_ms,
        "success": result.success,
    }


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_score_lead_task(self, tenant_id: str, user_id: str, lead_data: dict, correlation_id: str = None):
    """Score a lead using AI."""
    logger.info("AI score lead task", tenant_id=tenant_id)
    from app.services.ai.router import get_ai_router
    from app.core.tenant_context import tenant_db_context
    import asyncio

    prompt = f"""
    Analyze this lead and provide a score (0-100) with reasoning:
    Lead: {lead_data}
    
    Consider: company size, industry fit, engagement signals, budget indicators, authority.
    Return JSON: {{"score": 85, "reasoning": "...", "factors": ["...", "..."]}}
    """

    async def _run():
        router = get_ai_router()
        async with tenant_db_context(tenant_id) as db:
            result = await router.complete(
                task_type="lead_scoring",
                prompt=prompt,
                tenant_id=UUID(tenant_id),
                user_id=UUID(user_id) if user_id else None,
                correlation_id=correlation_id,
                response_format={"type": "json_object"},
                db=db,
            )
            await db.commit()
            return result

    result = asyncio.run(_run())
    return {
        "content": result.content,
        "provider": result.provider,
        "model": result.model,
        "tokens": result.total_tokens,
        "latency_ms": result.latency_ms,
        "success": result.success,
    }


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_generate_email_task(self, tenant_id: str, user_id: str, context: dict, correlation_id: str = None):
    """Generate personalized email using AI."""
    logger.info("AI generate email task", tenant_id=tenant_id)
    from app.services.ai.router import get_ai_router
    from app.core.tenant_context import tenant_db_context
    import asyncio

    prompt = f"""
    Write a personalized sales email for:
    {context}
    
    Tone: professional, concise, value-focused.
    Return JSON: {{"subject": "...", "body": "..."}}
    """

    async def _run():
        router = get_ai_router()
        async with tenant_db_context(tenant_id) as db:
            result = await router.complete(
                task_type="personalization",
                prompt=prompt,
                tenant_id=UUID(tenant_id),
                user_id=UUID(user_id) if user_id else None,
                correlation_id=correlation_id,
                response_format={"type": "json_object"},
                db=db,
            )
            await db.commit()
            return result

    result = asyncio.run(_run())
    return {
        "content": result.content,
        "provider": result.provider,
        "model": result.model,
        "tokens": result.total_tokens,
        "latency_ms": result.latency_ms,
        "success": result.success,
    }


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_analyze_reply_task(self, tenant_id: str, user_id: str, reply_text: str, context: dict, correlation_id: str = None):
    """Analyze inbound reply for intent and sentiment."""
    logger.info("AI analyze reply task", tenant_id=tenant_id)
    from app.services.ai.router import get_ai_router
    from app.core.tenant_context import tenant_db_context
    import asyncio

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

    async def _run():
        router = get_ai_router()
        async with tenant_db_context(tenant_id) as db:
            result = await router.complete(
                task_type="reply_analysis",
                prompt=prompt,
                tenant_id=UUID(tenant_id),
                user_id=UUID(user_id) if user_id else None,
                correlation_id=correlation_id,
                response_format={"type": "json_object"},
                db=db,
            )
            await db.commit()
            return result

    result = asyncio.run(_run())
    return {
        "content": result.content,
        "provider": result.provider,
        "model": result.model,
        "tokens": result.total_tokens,
        "latency_ms": result.latency_ms,
        "success": result.success,
    }


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_next_best_action_task(self, tenant_id: str, user_id: str, lead_data: dict, correlation_id: str = None):
    """Recommend next best action for a lead."""
    logger.info("AI next best action task", tenant_id=tenant_id)
    from app.services.ai.router import get_ai_router
    from app.core.tenant_context import tenant_db_context
    import asyncio

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

    async def _run():
        router = get_ai_router()
        async with tenant_db_context(tenant_id) as db:
            result = await router.complete(
                task_type="next_best_action",
                prompt=prompt,
                tenant_id=UUID(tenant_id),
                user_id=UUID(user_id) if user_id else None,
                correlation_id=correlation_id,
                response_format={"type": "json_object"},
                db=db,
            )
            await db.commit()
            return result

    result = asyncio.run(_run())
    return {
        "content": result.content,
        "provider": result.provider,
        "model": result.model,
        "tokens": result.total_tokens,
        "latency_ms": result.latency_ms,
        "success": result.success,
    }


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_generate_proposal_task(self, tenant_id: str, user_id: str, proposal_data: dict, correlation_id: str = None):
    """Generate a sales proposal."""
    logger.info("AI generate proposal task", tenant_id=tenant_id)
    from app.services.ai.router import get_ai_router
    from app.core.tenant_context import tenant_db_context
    import asyncio

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

    async def _run():
        router = get_ai_router()
        async with tenant_db_context(tenant_id) as db:
            result = await router.complete(
                task_type="proposal_generation",
                prompt=prompt,
                tenant_id=UUID(tenant_id),
                user_id=UUID(user_id) if user_id else None,
                correlation_id=correlation_id,
                response_format={"type": "json_object"},
                db=db,
            )
            await db.commit()
            return result

    result = asyncio.run(_run())
    return {
        "content": result.content,
        "provider": result.provider,
        "model": result.model,
        "tokens": result.total_tokens,
        "latency_ms": result.latency_ms,
        "success": result.success,
    }


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_lead_miner_task(self, tenant_id: str, user_id: str, icp_criteria: dict, correlation_id: str = None):
    """Run AI Lead Miner to find prospects."""
    logger.info("AI lead miner task", tenant_id=tenant_id)
    from app.services.ai.router import get_ai_router
    from app.core.tenant_context import tenant_db_context
    import asyncio

    prompt = f"""
    Find companies matching this ICP:
    {icp_criteria}
    
    Return JSON: {{
        "companies": [
            {{"name": "...", "website": "...", "founder": "...", "linkedin": "...", "email": "...", "location": "...", "size": "...", "score": 85, "reason": "..."}}
        ]
    }}
    """

    async def _run():
        router = get_ai_router()
        async with tenant_db_context(tenant_id) as db:
            result = await router.complete(
                task_type="lead_mining",
                prompt=prompt,
                tenant_id=UUID(tenant_id),
                user_id=UUID(user_id) if user_id else None,
                correlation_id=correlation_id,
                response_format={"type": "json_object"},
                db=db,
            )
            await db.commit()
            return result

    result = asyncio.run(_run())
    return {
        "content": result.content,
        "provider": result.provider,
        "model": result.model,
        "tokens": result.total_tokens,
        "latency_ms": result.latency_ms,
        "success": result.success,
    }


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_chat_assistant_task(self, tenant_id: str, user_id: str, message: str, context: dict, correlation_id: str = None):
    """Handle AI chat assistant request with tool calling."""
    logger.info("AI chat assistant task", tenant_id=tenant_id)
    from app.services.ai.router import get_ai_router
    from app.core.tenant_context import tenant_db_context
    import asyncio

    prompt = f"""
    You are Globexa AI Assistant. Help the user with CRM tasks.
    User message: {message}
    Context: {context}
    
    Available tools: search_leads, get_lead, create_campaign, assign_lead, schedule_followup, send_email, create_proposal, update_stage
    
    Respond with tool calls or direct answer.
    """

    async def _run():
        router = get_ai_router()
        async with tenant_db_context(tenant_id) as db:
            result = await router.complete(
                task_type="chat_assistant",
                prompt=prompt,
                tenant_id=UUID(tenant_id),
                user_id=UUID(user_id) if user_id else None,
                correlation_id=correlation_id,
                db=db,
            )
            await db.commit()
            return result

    result = asyncio.run(_run())
    return {
        "content": result.content,
        "provider": result.provider,
        "model": result.model,
        "tokens": result.total_tokens,
        "latency_ms": result.latency_ms,
        "success": result.success,
        "tool_calls": result.tool_calls,
    }