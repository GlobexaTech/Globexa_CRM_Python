"""Schema-validated AI nodes with durable, concurrent quota reservations and real usage."""
import json
import os
from datetime import timedelta
from sqlalchemy import select, func
from fastapi import HTTPException
from app.models import AIUsageLog, AutomationStepExecution, AITaskTypeEnum
from app.schemas.automation import DecisionOutput, IntelligenceOutput
from app.services.ai.gateway import AIGateway, CompatibleProvider, OllamaProvider, ModelRoute
from app.services.ai.safety import SYSTEM_INSTRUCTIONS, safe_data
from app.services.crm.common import authorize, serial_key, meter, now, audit
from app.services.automation.validation import policy


class AIUnavailable(RuntimeError):
    automation_code = "provider_unavailable"
    retryable = True
    uncertain = False
    retry_after = 10


def configured_gateway():
    from app.services.crm.ai import build_gateway
    primary = build_gateway()
    providers, routes = dict(primary.providers), list(primary.routes)
    name = os.environ.get("CRM_AI_FALLBACK_PROVIDER", "").strip().lower()
    if name:
        name = "ollama" if name == "local" else name
        model = os.environ.get("CRM_AI_FALLBACK_MODEL", "")
        url = os.environ.get("CRM_AI_FALLBACK_BASE_URL", "")
        key = os.environ.get("CRM_AI_FALLBACK_API_KEY", "")
        if name in providers or not model or not url or (name != "ollama" and not key):
            raise ValueError("Fallback requires a distinct explicitly configured provider, model and endpoint")
        providers[name] = OllamaProvider(url) if name == "ollama" else CompatibleProvider(url, key)
        routes.append(ModelRoute(name, model))
    return AIGateway(providers, routes)


async def execute_ai_node(db, execution, step, node, context, gateway=None):
    await authorize(db, execution.tenant_id, execution.actor_id, "ai:chat")
    limits = await policy(db, execution.tenant_id)
    try:
        instance = gateway or configured_gateway()
    except (RuntimeError, ValueError) as exc:
        raise AIUnavailable("Model configuration unavailable") from exc
    count = len(instance.routes)
    try:
        await serial_key(db, execution.tenant_id, "automation-ai-admission")
        reservations = select(func.coalesce(func.sum(AutomationStepExecution.input["ai_reserved"].as_integer()), 0)).where(
            AutomationStepExecution.tenant_id == execution.tenant_id, AutomationStepExecution.state == "RUNNING",
            AutomationStepExecution.id != step.id)
        reserved = await db.scalar(reservations)
        instant = now()
        for boundary, maximum in ((instant.replace(hour=0, minute=0, second=0, microsecond=0), limits.daily_ai_calls),
                                   (instant.replace(day=1, hour=0, minute=0, second=0, microsecond=0), limits.monthly_ai_calls)):
            used = await db.scalar(select(func.count()).select_from(AIUsageLog).where(AIUsageLog.tenant_id == execution.tenant_id, AIUsageLog.created_at >= boundary))
            if used + reserved + count > maximum: raise HTTPException(403, "Tenant AI call quota reached")
        used = await db.scalar(select(func.count()).select_from(AIUsageLog).where(AIUsageLog.tenant_id == execution.tenant_id, AIUsageLog.automation_execution_id == execution.id))
        if used + count > limits.max_ai_calls: raise HTTPException(403, "Execution AI call quota reached")
        await meter(db, execution.tenant_id, execution.actor_id, "ai_credits", count)
        step.input = {**step.input, "ai_reserved": count}
        await db.commit()  # FK parents and quota reservation must be visible to the independent usage ledger.
        args = step.input["arguments"]
        facts = {key: value for key, value in context.items() if key not in {"current_user", "automation", "before"}}
        # Data is bounded and sent as an explicit untrusted envelope, never tools or identity.
        safe_data(facts)
        if args.get("kind") == "research":
            from app.services.ai.research import research_web
            facts["research"] = await research_web(args["url"], [args["url"]])
            safe_data(facts["research"])
        schema = DecisionOutput if node.type == "ai_decision" else IntelligenceOutput
        result = await instance.execute(db, execution.tenant_id, execution.actor_id, AITaskTypeEnum.CLASSIFICATION,
            "chat", automation_execution_id=execution.id, automation_step_id=step.id,
            messages=[{"role": "system", "content": SYSTEM_INSTRUCTIONS + " Return only JSON matching: " + json.dumps(schema.model_json_schema())},
                      {"role": "user", "content": json.dumps({"kind": args.get("kind", "summarize"), "instruction": args.get("instruction", "Analyze supplied facts"), "UNTRUSTED_DATA": facts}, default=str)}],
            response_format={"type": "json_object"}, max_tokens=1500, temperature=0)
        output = schema.model_validate_json(result.content).model_dump(mode="json")
        safe_data(output)
        required = {"classify": "classification", "score": "score", "recommend": "recommendation", "draft": "draft", "extract": "extracted"}.get(args.get("kind"))
        if node.type != "ai_decision" and required and output.get(required) in (None, "", {}):
            raise HTTPException(422, "AI output is missing its required structured result")
        output.update(model=result.model, provider=result.provider, is_recommendation=True)
        audit(db, execution.tenant_id, execution.actor_id, "automation.ai.decision" if node.type == "ai_decision" else "automation.ai.completed", "automation_step", step.id)
        return output
    except RuntimeError as exc:
        failure = AIUnavailable("All configured AI providers failed")
        failure.retry_after = getattr(exc, "retry_after", 10)
        failure.retryable = getattr(exc, "retryable", True)
        raise failure from exc
    finally:
        execution.ai_calls = await db.scalar(select(func.count()).select_from(AIUsageLog).where(AIUsageLog.tenant_id == execution.tenant_id, AIUsageLog.automation_execution_id == execution.id))
        if gateway is None:
            for provider in instance.providers.values(): await provider.client.aclose()
