"""Supervisor decomposition and monitoring use persistent child executions."""

import json
from datetime import timedelta
from typing import Literal
from pydantic import Field
from sqlalchemy import select
from app.models import AgentExecution
from app.schemas.workforce import Strict, ExecutionInput
from app.services.crm.common import now, audit
from app.services.ai.safety import safe_data


class Subtask(Strict):
    agent_name: Literal["research", "lead_mining", "sales", "analyst", "support"]
    objective: str = Field(min_length=3, max_length=2000)


class Plan(Strict):
    summary: str = Field(max_length=4000)
    subtasks: list[Subtask] = Field(min_length=1, max_length=5)


class Summary(Strict):
    summary: str = Field(max_length=12000)


async def run_supervisor(db, row, *, gateway=None):
    from app.services.ai.agent import (
        AGENTS,
        call_model,
        request_execution,
        check_cancel,
        retry_execution,
    )

    data = ExecutionInput.model_validate(row.task)
    if not row.result or "child_ids" not in row.result:
        prompt = json.dumps(
            {
                "instruction": "Decompose this objective into at most five independent scoped subtasks. Return JSON matching the schema; subtasks inherit exactly the user-approved context and available tools. Do not invent target IDs or permissions.",
                "schema": Plan.model_json_schema(),
                "objective": data.objective,
                "agents": list(AGENTS)[:-1],
                "allowed_tools": data.tools,
                "UNTRUSTED_DATA": data.context.model_dump(mode="json"),
            }
        )
        response = await call_model(db, row, prompt, gateway=gateway)
        if await check_cancel(db, row):
            return {"execution_id": str(row.id), "state": "cancelled"}
        plan = Plan.model_validate_json(response.content)
        safe_data(plan.model_dump(mode="json"))
        children = []
        for index, subtask in enumerate(plan.subtasks):
            child = await request_execution(
                db,
                row.tenant_id,
                row.actor_id,
                ExecutionInput(
                    agent_name=subtask.agent_name,
                    objective=subtask.objective,
                    context=data.context,
                    tools=sorted(set(data.tools) & AGENTS[subtask.agent_name]["tools"]),
                ),
                f"supervisor:{row.id}:{index}",
                parent_id=row.id,
            )
            children.append(str(child.id))
        row.result = {
            "plan": plan.model_dump(mode="json"),
            "child_ids": children,
            "summary": "Work queued",
        }
        await db.commit()
        return {"pending": True, "execution_id": str(row.id), "children": children}
    children = (
        await db.scalars(
            select(AgentExecution)
            .where(AgentExecution.tenant_id == row.tenant_id, AgentExecution.parent_id == row.id)
            .order_by(AgentExecution.created_at)
        )
    ).all()
    if any(child.state in {"queued", "running"} for child in children):
        if row.started_at < now() - timedelta(minutes=10):
            from app.services.ai.agent import cancel_execution

            for child in children:
                if child.state in {"queued", "running"}:
                    await cancel_execution(db, row.tenant_id, row.actor_id, child.id)
            row.state, row.failed_at, row.error_message = "failed", now(), "child_execution_timeout"
            await db.commit()
            return {"execution_id": str(row.id), "state": "failed"}
        return {"pending": True, "execution_id": str(row.id)}
    for child in children:
        if (
            child.state == "failed"
            and child.error_message == "model_unavailable"
            and child.attempts < 2
            and not child.tools_used
        ):
            retry_key = f"supervisor-retry:{child.id}"
            existing = await db.scalar(
                select(AgentExecution.id).where(
                    AgentExecution.tenant_id == row.tenant_id,
                    AgentExecution.idempotency_key == retry_key,
                )
            )
            if not existing:
                await retry_execution(db, row.tenant_id, row.actor_id, child.id, retry_key)
                await db.commit()
                return {"pending": True, "execution_id": str(row.id)}
    results = [
        {
            "execution_id": str(child.id),
            "agent": child.agent_name,
            "state": child.state,
            "summary": (child.result or {}).get("summary"),
            "approvals": (child.result or {}).get("approvals", []),
            "error": child.error_message,
        }
        for child in children
    ]
    response = await call_model(
        db,
        row,
        json.dumps(
            {
                "instruction": "Summarize these actual child results. Clearly identify failures, cancellations and pending human approvals. Do not claim a proposed or approved action was delivered.",
                "schema": Summary.model_json_schema(),
                "UNTRUSTED_DATA": results,
            }
        ),
        gateway=gateway,
    )
    if await check_cancel(db, row):
        return {"execution_id": str(row.id), "state": "cancelled"}
    summary = Summary.model_validate_json(response.content)
    safe_data(summary.model_dump())
    row.result = {
        **row.result,
        "summary": summary.summary,
        "children": results,
        "approvals": list({approval for child in results for approval in child["approvals"]}),
    }
    row.state, row.completed_at = "completed", now()
    audit(db, row.tenant_id, row.actor_id, "supervisor.completed", "agent_execution", row.id)
    await db.commit()
    return {"execution_id": str(row.id), "state": row.state, "result": row.result}
