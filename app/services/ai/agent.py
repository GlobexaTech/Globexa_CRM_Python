"""Durable bounded agents. Identity and permissions are supplied only by server state."""

import json
import os
from uuid import UUID
from fastapi import HTTPException
from pydantic import Field, ValidationError
from sqlalchemy import select
from app.models import (
    AgentExecution,
    ApprovalRequest,
    Lead,
    Contact,
    Deal,
    Conversation,
    Campaign,
    AITaskTypeEnum,
)
from app.schemas.workforce import ExecutionInput, Strict
from app.services.crm.common import authorize, owned, serial_key, enqueue, audit, now, meter
from app.services.ai.safety import safe_data, SYSTEM_INSTRUCTIONS
from app.services.ai.workforce_tools import TOOL_SPECS, describe_tools, execute_tool

AGENTS = {
    "research": {
        "label": "Research Agent",
        "task": AITaskTypeEnum.RESEARCH,
        "tools": {"research_web", "search_leads", "get_lead", "get_customer", "create_note"},
    },
    "lead_mining": {
        "label": "Lead Mining Agent",
        "task": AITaskTypeEnum.LEAD_MINING,
        "tools": {
            "research_web",
            "search_leads",
            "search_contacts",
            "get_customer",
            "create_lead",
            "create_note",
        },
    },
    "sales": {
        "label": "Sales Agent",
        "task": AITaskTypeEnum.NEXT_BEST_ACTION,
        "tools": {
            "search_leads",
            "get_lead",
            "get_customer",
            "get_pipeline",
            "get_deal",
            "update_lead",
            "create_task",
            "update_task",
            "create_note",
            "draft_email",
            "send_email",
            "get_conversation",
        },
    },
    "analyst": {
        "label": "CRM Analyst",
        "task": AITaskTypeEnum.SUMMARIZATION,
        "tools": {"search_analytics", "get_pipeline", "get_deal", "get_lead", "create_note"},
    },
    "support": {
        "label": "Support Agent",
        "task": AITaskTypeEnum.REPLY_ANALYSIS,
        "tools": {
            "get_conversation",
            "get_customer",
            "create_task",
            "create_note",
            "draft_email",
            "send_email",
        },
    },
    "supervisor": {
        "label": "Supervisor",
        "task": AITaskTypeEnum.ROUTING_DECISION,
        "tools": set(TOOL_SPECS),
    },
}


class ToolAction(Strict):
    name: str
    arguments: dict


class AgentOutput(Strict):
    summary: str = Field(max_length=12000)
    actions: list[ToolAction] = Field(default_factory=list, max_length=8)


async def validate_context(db, tenant_id, actor_id, context):
    if context.entity_id:
        model, permission = {
            "lead": (Lead, "leads:read"),
            "contact": (Contact, "contacts:read"),
            "deal": (Deal, "deals:read"),
            "conversation": (Conversation, "conversations:read"),
            "campaign": (Campaign, "campaigns:read"),
        }[context.entity_type]
        await authorize(db, tenant_id, actor_id, permission)
        await owned(db, model, tenant_id, context.entity_id)
    for url in context.research_urls:
        from app.services.ai.research import validate_url

        validate_url(url, context.research_urls)


async def request_execution(db, tenant_id, actor_id, data, key, *, parent_id=None, attempts=0):
    await authorize(db, tenant_id, actor_id, "ai:chat")
    safe_data(data.model_dump(mode="json"))
    await validate_context(db, tenant_id, actor_id, data.context)
    if set(data.tools) - AGENTS[data.agent_name]["tools"]:
        raise HTTPException(422, "Tool is outside this agent capability set")
    for name in data.tools:
        await authorize(db, tenant_id, actor_id, TOOL_SPECS[name][0])
    values = data.model_dump(mode="json")
    await serial_key(db, tenant_id, "agent:" + key)
    row = await db.scalar(
        select(AgentExecution).where(
            AgentExecution.tenant_id == tenant_id, AgentExecution.idempotency_key == key
        )
    )
    if row:
        if row.actor_id != actor_id or row.task != values:
            raise HTTPException(409, "Execution idempotency key has different input")
        return row
    row = AgentExecution(
        tenant_id=tenant_id,
        actor_id=actor_id,
        agent_name=data.agent_name,
        task_type=AGENTS[data.agent_name]["task"].value,
        task=values,
        idempotency_key=key,
        parent_id=parent_id,
        attempts=attempts,
    )
    db.add(row)
    await db.flush()
    job, _ = await enqueue(
        db, tenant_id, actor_id, "workforce", "agent:" + str(row.id), {"execution_id": str(row.id)}
    )
    row.job_id = job.id
    audit(db, tenant_id, actor_id, "agent.queued", "agent_execution", row.id)
    await db.flush()
    return row


async def visible_execution(db, tenant_id, actor_id, execution_id, lock=False):
    from app.core.rbac import get_role_permissions

    member = await authorize(db, tenant_id, actor_id, "ai:chat")
    row = await owned(db, AgentExecution, tenant_id, execution_id, lock)
    if row.actor_id != actor_id and "ai:approve" not in get_role_permissions(member.role):
        raise HTTPException(404, "Execution not found")
    return row


async def cancel_execution(db, tenant_id, actor_id, execution_id):
    row = await visible_execution(db, tenant_id, actor_id, execution_id, True)
    if row.state in {"completed", "failed", "cancelled"}:
        if row.state == "cancelled":
            return row
        raise HTTPException(409, "Execution is already terminal")
    rows = [row] + list(
        (
            await db.scalars(
                select(AgentExecution)
                .where(AgentExecution.tenant_id == tenant_id, AgentExecution.parent_id == row.id)
                .with_for_update()
            )
        ).all()
    )
    for item in rows:
        if item.state in {"queued", "running"}:
            item.cancel_requested, item.state, item.completed_at = True, "cancelled", now()
            approvals = (
                await db.scalars(
                    select(ApprovalRequest).where(
                        ApprovalRequest.tenant_id == tenant_id,
                        ApprovalRequest.execution_id == item.id,
                        ApprovalRequest.status.in_(["pending", "approved"]),
                    )
                )
            ).all()
            for approval in approvals:
                if not approval.execution_result:
                    approval.status = "expired"
            audit(db, tenant_id, actor_id, "agent.cancelled", "agent_execution", item.id)
    await db.flush()
    return row


async def retry_execution(db, tenant_id, actor_id, execution_id, key):
    row = await visible_execution(db, tenant_id, actor_id, execution_id)
    if (
        row.state != "failed"
        or row.tools_used
        or row.attempts >= 2
        or row.error_message not in {"model_unavailable", "provider_unavailable"}
    ):
        raise HTTPException(409, "Execution cannot be retried safely")
    return await request_execution(
        db,
        tenant_id,
        actor_id,
        ExecutionInput.model_validate(row.task),
        key,
        parent_id=row.parent_id,
        attempts=row.attempts + 1,
    )


async def call_model(db, execution, prompt, *, gateway=None):
    await authorize(db, execution.tenant_id, execution.actor_id, "ai:chat")
    await meter(db, execution.tenant_id, execution.actor_id, "ai_credits")
    await db.commit()
    temporary = gateway is None
    if gateway is None:
        from app.services.crm.ai import build_gateway

        try:
            gateway = build_gateway()
        except RuntimeError as exc:
            raise RuntimeError("model_unavailable") from exc
    try:
        result = await gateway.execute(
            db,
            execution.tenant_id,
            execution.actor_id,
            AGENTS[execution.agent_name]["task"],
            "chat",
            execution_id=execution.id,
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2500,
            response_format={"type": "json_object"},
        )
        execution.provider, execution.model = result.provider, result.model
        await db.commit()
        return result
    finally:
        if temporary:
            for provider in gateway.providers.values():
                client = getattr(provider, "client", None)
                if client:
                    await client.aclose()


async def check_cancel(db, row):
    await db.refresh(row)
    if row.cancel_requested or row.state == "cancelled":
        return True
    await authorize(db, row.tenant_id, row.actor_id, "ai:chat")
    return False


async def run_execution(db, job, gateway=None):
    from app.services.ai.memory import store_working, recall

    row = await owned(db, AgentExecution, job.tenant_id, UUID(job.payload["execution_id"]))
    if row.actor_id != job.actor_id:
        raise HTTPException(403, "Execution identity mismatch")
    if row.state in {"completed", "failed", "cancelled"}:
        return {"execution_id": str(row.id), "state": row.state}
    if await check_cancel(db, row):
        return {"execution_id": str(row.id), "state": "cancelled"}
    data = ExecutionInput.model_validate(row.task)
    try:
        await validate_context(db, row.tenant_id, row.actor_id, data.context)
        row.state = "running"
        row.started_at = row.started_at or now()
        await store_working(db, row, {"state": "running"})
        await db.commit()
        if row.agent_name == "supervisor":
            from app.services.ai.supervisor import run_supervisor

            return await run_supervisor(db, row, gateway=gateway)
        memory = await recall(db, row.tenant_id, row.actor_id, row.agent_name)
        safe_data(memory)
        observations = []
        approvals = []
        summary = ""
        for turn in range(3):
            if await check_cancel(db, row):
                return {"execution_id": str(row.id), "state": "cancelled"}
            prompt = json.dumps(
                {
                    "agent": row.agent_name,
                    "objective": data.objective,
                    "allowed_tools": describe_tools(data.tools),
                    "UNTRUSTED_DATA": {
                        "context": data.context.model_dump(mode="json"),
                        "approved_memory": memory,
                        "observations": observations,
                    },
                },
                default=str,
            )
            result = await call_model(db, row, prompt, gateway=gateway)
            if await check_cancel(db, row):
                return {"execution_id": str(row.id), "state": "cancelled"}
            output = AgentOutput.model_validate_json(result.content)
            safe_data(output.model_dump(mode="json"))
            summary = output.summary
            if not output.actions:
                break
            if turn == 2 or len(row.tools_used) + len(output.actions) > 8:
                raise HTTPException(422, "Agent tool budget exhausted")
            for index, action in enumerate(output.actions):
                if await check_cancel(db, row):
                    return {"execution_id": str(row.id), "state": "cancelled"}
                tool_result = await execute_tool(
                    db,
                    row.tenant_id,
                    row.actor_id,
                    action.name,
                    action.arguments,
                    f"{row.id}:{turn}:{index}",
                    execution=row,
                    allowed_tools=data.tools,
                    research_urls=data.context.research_urls,
                )
                row.tools_used = [*row.tools_used, action.name]
                observations.append({"tool": action.name, "result": tool_result})
                if tool_result.get("approval_id"):
                    approvals.append(tool_result["approval_id"])
                await db.commit()
        row.result = {"summary": summary, "observations": observations, "approvals": approvals}
        row.state, row.completed_at = "completed", now()
        await store_working(db, row, {"state": row.state, "tool_names": row.tools_used})
        audit(db, row.tenant_id, row.actor_id, "agent.completed", "agent_execution", row.id)
        await db.commit()
    except (
        HTTPException,
        ValidationError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        TimeoutError,
    ) as exc:
        await db.rollback()
        row = await owned(db, AgentExecution, job.tenant_id, UUID(job.payload["execution_id"]))
        if row.cancel_requested:
            row.state, row.completed_at = "cancelled", now()
        else:
            code = (
                "model_unavailable"
                if isinstance(exc, RuntimeError) and str(exc) == "model_unavailable"
                else "execution_rejected"
            )
            row.state, row.failed_at, row.error_message = "failed", now(), code
            audit(db, row.tenant_id, row.actor_id, "agent.failed", "agent_execution", row.id, False)
        await db.commit()
    return {"execution_id": str(row.id), "state": row.state, "result": row.result}


class WorkforceSubscriber:
    name = "ai_workforce"
    event_types = {"lead.created", "message.received", "deal.stage_changed", "campaign.completed"}

    async def handle(self, db, event):
        # Explicit opt-in: runtime configuration never grants an actor permission.
        if (
            os.environ.get("WORKFORCE_EVENT_TRIGGERS", "").lower() != "true"
            or not event.actor_id
            or int(event.payload.get("_depth", 0)) >= 2
        ):
            return
        mapping = {
            "lead.created": (
                "research",
                "lead",
                "Review and summarize the newly created lead",
                ["get_lead"],
            ),
            "message.received": (
                "support",
                "conversation",
                "Analyze the received customer message",
                ["get_conversation"],
            ),
            "deal.stage_changed": (
                "sales",
                "deal",
                "Suggest the next best action for this deal",
                ["get_deal"],
            ),
            "campaign.completed": (
                "analyst",
                "campaign",
                "Analyze the completed campaign",
                ["search_analytics"],
            ),
        }
        agent, kind, objective, tools = mapping[event.event_type]
        entity = (
            event.payload.get("conversation_id")
            if event.event_type == "message.received"
            else event.aggregate_id
        )
        if not entity:
            return
        try:
            async with db.begin_nested():
                await request_execution(
                    db,
                    event.tenant_id,
                    event.actor_id,
                    ExecutionInput(
                        agent_name=agent,
                        objective=objective,
                        context={"entity_type": kind, "entity_id": entity},
                        tools=tools,
                    ),
                    "event:" + str(event.id),
                )
        except HTTPException as exc:
            if exc.status_code not in (403, 404):
                raise
            audit(
                db,
                event.tenant_id,
                event.actor_id,
                "agent.event.denied",
                "domain_event",
                event.id,
                False,
            )
