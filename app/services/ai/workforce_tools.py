"""Sixteen bounded tools share CRM services, live membership and tenant ownership checks."""

from typing import Annotated, Literal
from uuid import UUID
from fastapi import HTTPException
from pydantic import Field, EmailStr
from sqlalchemy import select
from app.schemas.workforce import Strict
from app.models import Lead, Contact, Deal, Task, Pipeline, Conversation, Message, Integration
from app.models import LeadStatusEnum, TaskStatusEnum, TaskPriorityEnum
from app.services.crm.common import authorize, owned, enqueue, audit, now
from app.services.crm.automation import perform_action, relations
from app.services.ai.safety import safe_data


class Query(Strict):
    query: str = Field(min_length=1, max_length=200)


class LeadID(Strict):
    lead_id: UUID


class ContactID(Strict):
    contact_id: UUID


class PipelineID(Strict):
    pipeline_id: UUID


class DealID(Strict):
    deal_id: UUID


class ConversationID(Strict):
    conversation_id: UUID


class LeadCreate(Strict):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(None, max_length=8000)
    contact_id: UUID | None = None
    company_id: UUID | None = None


class LeadUpdate(Strict):
    entity_id: UUID
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=8000)
    status: LeadStatusEnum | None = None


class TaskCreate(Strict):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(None, max_length=8000)
    lead_id: UUID | None = None
    deal_id: UUID | None = None
    contact_id: UUID | None = None
    company_id: UUID | None = None
    priority: TaskPriorityEnum = TaskPriorityEnum.MEDIUM


class TaskUpdate(Strict):
    task_id: UUID
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=8000)
    status: TaskStatusEnum | None = None
    priority: TaskPriorityEnum | None = None


class NoteCreate(Strict):
    content: str = Field(min_length=1, max_length=8000)
    lead_id: UUID | None = None
    deal_id: UUID | None = None
    contact_id: UUID | None = None
    company_id: UUID | None = None


class DraftEmail(Strict):
    conversation_id: UUID
    body: str = Field(min_length=1, max_length=12000)


class SendEmail(DraftEmail):
    recipient: EmailStr | Annotated[str, Field(pattern=r"^\+[1-9][0-9]{6,14}$")]
    attachments: list = Field(default_factory=list, max_length=0)


class Analytics(Strict):
    view: Literal["pipeline", "conversion", "campaigns", "activity", "ai", "dashboard"]


class Research(Strict):
    url: str = Field(min_length=8, max_length=1000)


# There is no model-provided tenant, actor, URL base, SQL or permission field.
TOOL_SPECS = {
    "search_leads": ("leads:read", Query, False),
    "get_lead": ("leads:read", LeadID, False),
    "create_lead": ("leads:write", LeadCreate, True),
    "update_lead": ("leads:write", LeadUpdate, True),
    "search_contacts": ("contacts:read", Query, False),
    "get_customer": ("contacts:read", ContactID, False),
    "get_pipeline": ("deals:read", PipelineID, False),
    "get_deal": ("deals:read", DealID, False),
    "create_task": ("tasks:write", TaskCreate, True),
    "update_task": ("tasks:write", TaskUpdate, True),
    "create_note": ("notes:write", NoteCreate, True),
    "get_conversation": ("conversations:read", ConversationID, False),
    "draft_email": ("ai:draft_email", DraftEmail, True),
    "send_email": ("ai:send_email", SendEmail, True),
    "search_analytics": ("analytics:read", Analytics, False),
    "research_web": ("ai:chat", Research, False),
}


def describe_tools(names):
    return [
        {
            "name": name,
            "arguments": TOOL_SPECS[name][1].model_json_schema(),
            "requires_approval": TOOL_SPECS[name][2],
        }
        for name in names
    ]


def validate_arguments(name, arguments):
    if name not in TOOL_SPECS:
        raise HTTPException(422, "Unknown workforce tool")
    safe_data(arguments)
    return TOOL_SPECS[name][1].model_validate(arguments).model_dump(mode="json", exclude_none=True)


async def validate_ownership(db, tenant_id, actor_id, name, arguments):
    await authorize(db, tenant_id, actor_id, TOOL_SPECS[name][0])
    models = {
        "lead_id": Lead,
        "contact_id": Contact,
        "deal_id": Deal,
        "task_id": Task,
        "pipeline_id": Pipeline,
        "conversation_id": Conversation,
    }
    for field, model in models.items():
        if arguments.get(field):
            await owned(db, model, tenant_id, UUID(arguments[field]))
    if name == "update_lead":
        await owned(db, Lead, tenant_id, UUID(arguments["entity_id"]))
    await relations(
        db,
        tenant_id,
        {
            k: UUID(v)
            for k, v in arguments.items()
            if k in {"lead_id", "deal_id", "contact_id", "company_id"} and v
        },
    )
    if name in {"draft_email", "send_email"}:
        await authorize(
            db,
            tenant_id,
            actor_id,
            "conversations:write" if name == "draft_email" else "conversations:send",
        )


async def action_binding(db, tenant_id, name, arguments):
    if name != "send_email":
        return {}
    row = await owned(db, Conversation, tenant_id, UUID(arguments["conversation_id"]), True)
    if not row.integration_id:
        raise HTTPException(409, "Conversation has no configured provider")
    integration = await owned(db, Integration, tenant_id, row.integration_id, True)
    await db.flush()
    await db.refresh(row)
    await db.refresh(integration)
    from app.models import OAuthToken, IntegrationCredential
    import hashlib
    import json

    token = await db.scalar(
        select(OAuthToken)
        .where(OAuthToken.tenant_id == tenant_id, OAuthToken.integration_id == integration.id)
        .order_by(OAuthToken.created_at.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    credential = (
        None
        if token
        else await db.scalar(
            select(IntegrationCredential)
            .where(
                IntegrationCredential.tenant_id == tenant_id,
                IntegrationCredential.integration_id == integration.id,
                IntegrationCredential.is_active.is_(True),
            )
            .order_by(IntegrationCredential.created_at.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
    )
    # Reconnection/token replacement may switch sender accounts. No secret enters
    # approval JSON; a grant change conservatively requires a fresh approval.
    grant = (
        [str(token.id), token.access_token, token.refresh_token]
        if token
        else [
            str(credential.id),
            credential.credentials_encrypted,
            credential.access_token,
            credential.refresh_token,
        ]
        if credential
        else []
    )
    grant_hash = hashlib.sha256(json.dumps(grant, sort_keys=True).encode()).hexdigest()
    return {
        "integration_id": str(integration.id),
        "provider": (integration.config or {}).get("provider")
        or getattr(integration.type, "value", integration.type),
        "integration_type": getattr(integration.type, "value", integration.type),
        "configuration": integration.config or {},
        "credential_fingerprint": grant_hash,
        "subject": row.subject,
        "thread_id": row.provider_thread_id,
        "channel": row.channel,
    }


async def execute_tool(
    db,
    tenant_id,
    actor_id,
    name,
    arguments,
    key,
    *,
    execution=None,
    approved=False,
    allowed_tools=None,
    research_urls=(),
):
    if allowed_tools is not None and name not in allowed_tools:
        raise HTTPException(403, "Tool outside the user-approved execution scope")
    arguments = validate_arguments(name, arguments)
    await validate_ownership(db, tenant_id, actor_id, name, arguments)
    mutation = TOOL_SPECS[name][2]
    if mutation and not approved:
        from app.services.ai.approval import request_approval

        row = await request_approval(
            db,
            tenant_id,
            actor_id,
            execution.agent_name if execution else "supervisor",
            name,
            arguments,
            key,
            execution_id=execution.id if execution else None,
        )
        return {"approval_id": str(row.id), "status": row.status, "action_hash": row.action_hash}
    result = None
    if mutation:
        job, created = await enqueue(
            db,
            tenant_id,
            actor_id,
            "workforce_tool",
            "workforce-tool:" + key,
            {"name": name, "arguments": arguments},
        )
        if not created:
            if job.status != "completed":
                raise HTTPException(409, "Tool execution is already in progress")
            return job.result
    if name in {"search_leads", "search_contacts"}:
        from app.core.search import PostgresSearch

        result = {
            "items": await PostgresSearch(db).search(
                tenant_id, "leads" if name == "search_leads" else "contacts", arguments["query"], 20
            )
        }
    elif name in {"get_lead", "get_deal"}:
        model, field = (Lead, "lead_id") if name == "get_lead" else (Deal, "deal_id")
        row = await owned(db, model, tenant_id, UUID(arguments[field]))
        result = {
            k: str(getattr(row, k))
            if k.endswith("_id")
            else getattr(getattr(row, k), "value", getattr(row, k))
            for k in ("id", "title", "description", "status" if model is Lead else "value")
        }
        result["id"] = str(row.id)
    elif name == "get_customer":
        from app.services.crm.customer import customer360

        result = await customer360(
            db, tenant_id, actor_id, "contacts", UUID(arguments["contact_id"]), 20, 0
        )
    elif name == "get_pipeline":
        from app.models import Stage

        row = await owned(db, Pipeline, tenant_id, UUID(arguments["pipeline_id"]))
        stages = (
            await db.scalars(
                select(Stage)
                .where(Stage.tenant_id == tenant_id, Stage.pipeline_id == row.id)
                .order_by(Stage.order)
            )
        ).all()
        result = {
            "id": str(row.id),
            "name": row.name,
            "stages": [{"id": str(s.id), "name": s.name, "order": s.order} for s in stages],
        }
    elif name == "get_conversation":
        row = await owned(db, Conversation, tenant_id, UUID(arguments["conversation_id"]))
        messages = (
            await db.scalars(
                select(Message)
                .where(Message.tenant_id == tenant_id, Message.conversation_id == row.id)
                .order_by(Message.created_at.desc())
                .limit(10)
            )
        ).all()
        result = {
            "id": str(row.id),
            "subject": row.subject,
            "messages": [
                {
                    "id": str(m.id),
                    "body": m.body[:4000],
                    "direction": m.direction,
                    "status": m.status,
                }
                for m in messages
            ],
            "untrusted": True,
        }
    elif name == "search_analytics":
        from app.services.crm.analytics import analytics

        result = await analytics(db, tenant_id, actor_id, arguments["view"])
    elif name == "research_web":
        from app.services.ai.research import research_web

        result = await research_web(arguments["url"], research_urls)
    elif name == "create_lead":
        from app.schemas import LeadCreate as Schema

        values = Schema.model_validate(arguments).model_dump()
        values["owner_id"] = actor_id
        row = Lead(tenant_id=tenant_id, **values)
        db.add(row)
        await db.flush()
        result = {"id": str(row.id)}
    elif name == "update_task":
        row = await owned(db, Task, tenant_id, UUID(arguments["task_id"]), True)
        from app.schemas import TaskUpdate as Schema

        values = Schema.model_validate(
            {k: v for k, v in arguments.items() if k != "task_id"}
        ).model_dump(exclude_unset=True)
        for field, value in values.items():
            setattr(row, field, value)
        if row.status == TaskStatusEnum.COMPLETED:
            row.completed_at = now()
        result = {"id": str(row.id)}
    elif name == "draft_email":
        row = Message(
            tenant_id=tenant_id,
            conversation_id=UUID(arguments["conversation_id"]),
            body=arguments["body"],
            direction="outbound",
            status="draft",
        )
        db.add(row)
        await db.flush()
        result = {"id": str(row.id), "status": "draft"}
    elif name == "send_email":
        from app.services.crm.conversations import queue_message
        from app.schemas.operations import MessageInput

        child = await queue_message(
            db,
            tenant_id,
            actor_id,
            UUID(arguments["conversation_id"]),
            MessageInput.model_validate(
                {k: v for k, v in arguments.items() if k != "conversation_id"}
            ),
            "approved:" + key,
        )
        result = {"job_id": str(child.id), "status": child.status}
    else:
        result = await perform_action(
            db, tenant_id, actor_id, "add_note" if name == "create_note" else name, arguments, key
        )
    from fastapi.encoders import jsonable_encoder

    result = jsonable_encoder(result)
    # Output identity fields are facts, not authorization overrides. Inspect external
    # text without treating an ordinary CRM user_id field as a model instruction.
    from app.services.ai.safety import INJECTION
    import json

    if INJECTION.search(json.dumps(result)):
        raise HTTPException(422, "Unsafe instruction in external tool content")
    if len(json.dumps(result)) > 24000:
        raise HTTPException(
            422, "Tool result exceeds the bounded context limit; narrow the request"
        )
    if mutation:
        job.status, job.result = "completed", result
    audit(
        db,
        tenant_id,
        actor_id,
        "workforce.tool." + name,
        "agent_execution",
        execution.id if execution else key,
    )
    await db.flush()
    return result
