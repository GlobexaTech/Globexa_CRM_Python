"""Approved CRM tools share validated services and never accept arbitrary SQL."""

from uuid import UUID
from sqlalchemy import select
from fastapi import HTTPException
from app.models import Pipeline, Stage, Message, Conversation
from app.services.crm.common import authorize, owned, enqueue, audit
from app.services.crm.automation import perform_action
from app.services.crm.customer import customer360
from app.core.search import PostgresSearch

PERMISSIONS = {
    "search_leads": "leads:read",
    "get_customer": "contacts:read",
    "get_pipeline": "deals:read",
    "create_task": "tasks:write",
    "update_lead": "leads:write",
    "create_note": "notes:write",
    "draft_email": "ai:draft_email",
}


async def execute_tool(db, tenant_id, actor_id, name, arguments, key):
    if name not in PERMISSIONS:
        raise HTTPException(422, "Tool is not approved")
    await authorize(db, tenant_id, actor_id, PERMISSIONS[name])
    if name == "search_leads":
        if set(arguments) != {"query"}:
            raise HTTPException(422, "Tool requires query")
        return {
            "items": await PostgresSearch(db).search(
                tenant_id, "leads", str(arguments["query"]), 20
            )
        }
    if name == "get_customer":
        if set(arguments) != {"contact_id"}:
            raise HTTPException(422, "Tool requires contact_id")
        return await customer360(
            db, tenant_id, actor_id, "contacts", UUID(arguments["contact_id"])
        )
    if name == "get_pipeline":
        if set(arguments) != {"pipeline_id"}:
            raise HTTPException(422, "Tool requires pipeline_id")
        row = await owned(db, Pipeline, tenant_id, UUID(arguments["pipeline_id"]))
        stages = (
            await db.scalars(
                select(Stage)
                .where(Stage.tenant_id == tenant_id, Stage.pipeline_id == row.id)
                .order_by(Stage.order)
            )
        ).all()
        return {
            "id": str(row.id),
            "name": row.name,
            "stages": [{"id": str(s.id), "name": s.name} for s in stages],
        }
    job, created = await enqueue(
        db,
        tenant_id,
        actor_id,
        "tool",
        "tool:" + key,
        {"name": name, "arguments": arguments},
    )
    if not created:
        return job.result
    if name == "draft_email":
        if (
            set(arguments) != {"conversation_id", "body"}
            or not isinstance(arguments["body"], str)
            or not 1 <= len(arguments["body"]) <= 100000
        ):
            raise HTTPException(422, "Draft requires conversation_id and bounded body")
        await authorize(db, tenant_id, actor_id, "conversations:write")
        conversation = await owned(
            db, Conversation, tenant_id, UUID(arguments["conversation_id"])
        )
        row = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            body=arguments["body"],
            direction="outbound",
            status="draft",
        )
        db.add(row)
        await db.flush()
        result = {"id": str(row.id), "status": "draft"}
    else:
        result = await perform_action(
            db,
            tenant_id,
            actor_id,
            "add_note" if name == "create_note" else name,
            arguments,
            key,
        )
    job.status, job.result = "completed", result
    audit(db, tenant_id, actor_id, "tool." + name, "operation_job", job.id)
    return result
