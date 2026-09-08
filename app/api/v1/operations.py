"""Frontend CRM contracts; shared services enforce permissions again in workers."""

from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime
from fastapi import APIRouter, Depends, Header, Query, HTTPException
from sqlalchemy import select, func
from app.core.database import get_db
from app.api.deps import get_current_active_user
from app.models import (
    Conversation,
    Message,
    Participant,
    Workflow,
    ExecutionLog,
    WorkflowRevision,
    OperationJob,
    Integration,
    OAuthToken,
    Activity,
    DomainEvent,
)
from app.schemas.operations import (
    Page,
    ConversationInput,
    ConversationResponse,
    MessageInput,
    MessageResponse,
    CampaignPlan,
    ScheduleInput,
    WorkflowInput,
    ToggleInput,
    AIRequest,
    OAuthCallback,
    ActivityInput,
    JobResponse,
)
from app.services.crm.common import owned, authorize, public_job, audit, now
from app.services.crm.conversations import create_conversation, queue_message
from app.services.crm.campaigns import configure_campaign, transition, update_stats
from app.services.crm.automation import save_workflow, toggle_workflow, relations
from app.services.crm.integrations import (
    start_oauth,
    finish_oauth,
    disconnect,
    request_sync,
    access_token,
)
from app.services.crm.providers import adapters, adapter_for
from app.services.crm.ai import request_ai
from app.services.crm.customer import customer360
from app.services.crm.analytics import analytics

router = APIRouter(prefix="/operations", tags=["CRM operations"])


async def identity(current=Depends(get_current_active_user)):
    return current[1].tenant_id, current[0].id


def idempotency_key(
    value: str = Header(alias="Idempotency-Key", min_length=8, max_length=100),
):
    return value


async def page(db, model, query, limit, offset, serializer):
    count = await db.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    )
    rows = (await db.scalars(query.limit(limit).offset(offset))).all()
    return {
        "items": [serializer(row) for row in rows],
        "total": count,
        "limit": limit,
        "offset": offset,
    }


@router.get("/customers/{kind}/{entity_id}", response_model=dict)
@router.get("/customers/{kind}/{entity_id}/timeline", response_model=dict)
async def customer(
    kind: Literal["contacts", "companies", "leads"],
    entity_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    actor=Depends(identity),
    db=Depends(get_db),
):
    return await customer360(db, *actor, kind, entity_id, limit, offset)


@router.post("/customers/{kind}/{entity_id}/export", response_model=dict)
async def customer_export(
    kind: Literal["contacts", "companies", "leads"],
    entity_id: UUID,
    actor=Depends(identity),
    db=Depends(get_db),
):
    await authorize(db, *actor, "leads:export")
    result = await customer360(db, *actor, kind, entity_id, 100, 0)
    audit(db, *actor, "customer.exported", kind, entity_id)
    await db.commit()
    return result


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def conversation_create(
    data: ConversationInput, actor=Depends(identity), db=Depends(get_db)
):
    row = await create_conversation(db, *actor, data)
    await db.commit()
    return ConversationResponse.model_validate(row)


@router.get("/conversations", response_model=Page)
async def conversations(
    q: str = Query("", max_length=200),
    channel: Literal["email", "whatsapp", "social"] | None = None,
    unread: bool = False,
    sort: Literal["newest", "oldest", "subject"] = "newest",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    actor=Depends(identity),
    db=Depends(get_db),
):
    await authorize(db, *actor, "conversations:read")
    query = select(Conversation).where(Conversation.tenant_id == actor[0])
    if q:
        query = query.where(
            Conversation.subject.ilike(
                "%" + q.replace("%", "\\%").replace("_", "\\_") + "%"
            )
        )
    if channel:
        query = query.where(Conversation.channel == channel)
    if unread:
        query = query.where(Conversation.unread_count > 0)
    order = {
        "newest": Conversation.created_at.desc(),
        "oldest": Conversation.created_at.asc(),
        "subject": Conversation.subject.asc(),
    }[sort]
    return await page(
        db,
        Conversation,
        query.order_by(order, Conversation.id),
        limit,
        offset,
        lambda row: ConversationResponse.model_validate(row).model_dump(),
    )


@router.get("/conversations/{conversation_id}", response_model=dict)
async def conversation_detail(
    conversation_id: UUID, actor=Depends(identity), db=Depends(get_db)
):
    await authorize(db, *actor, "conversations:read")
    row = await owned(db, Conversation, actor[0], conversation_id)
    people = (
        await db.scalars(
            select(Participant)
            .where(
                Participant.tenant_id == actor[0], Participant.conversation_id == row.id
            )
            .limit(100)
        )
    ).all()
    return {
        "conversation": ConversationResponse.model_validate(row).model_dump(),
        "participants": [{"address": p.address, "name": p.name} for p in people],
    }


@router.get("/conversations/{conversation_id}/messages", response_model=Page)
async def messages(
    conversation_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    direction: Literal["inbound", "outbound"] | None = None,
    actor=Depends(identity),
    db=Depends(get_db),
):
    await authorize(db, *actor, "conversations:read")
    await owned(db, Conversation, actor[0], conversation_id)
    query = select(Message).where(
        Message.tenant_id == actor[0], Message.conversation_id == conversation_id
    )
    if direction:
        query = query.where(Message.direction == direction)
    return await page(
        db,
        Message,
        query.order_by(Message.occurred_at, Message.id),
        limit,
        offset,
        lambda row: MessageResponse.model_validate(row).model_dump(),
    )


@router.post("/conversations/{conversation_id}/read", response_model=dict)
async def read_conversation(
    conversation_id: UUID, actor=Depends(identity), db=Depends(get_db)
):
    await authorize(db, *actor, "conversations:read")
    row = await owned(db, Conversation, actor[0], conversation_id, True)
    row.unread_count = 0
    await db.commit()
    return {"unread_count": 0}


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=JobResponse,
    status_code=202,
)
async def send_message(
    conversation_id: UUID,
    data: MessageInput,
    key=Depends(idempotency_key),
    actor=Depends(identity),
    db=Depends(get_db),
):
    job = await queue_message(db, *actor, conversation_id, data, key)
    await db.commit()
    return public_job(job)


@router.put("/campaigns/{campaign_id}/plan", response_model=dict)
async def campaign_plan(
    campaign_id: UUID, data: CampaignPlan, actor=Depends(identity), db=Depends(get_db)
):
    result = await configure_campaign(db, *actor, campaign_id, data)
    await db.commit()
    return result


@router.post("/campaigns/{campaign_id}/schedule", response_model=dict)
async def campaign_schedule(
    campaign_id: UUID, data: ScheduleInput, actor=Depends(identity), db=Depends(get_db)
):
    result = await transition(db, *actor, campaign_id, "schedule", data.scheduled_at)
    await db.commit()
    return result


@router.post("/campaigns/{campaign_id}/{operation}", response_model=dict)
async def campaign_transition(
    campaign_id: UUID,
    operation: Literal["launch", "pause", "resume", "cancel"],
    actor=Depends(identity),
    db=Depends(get_db),
):
    result = await transition(db, *actor, campaign_id, operation)
    await db.commit()
    return result


@router.get("/campaigns/{campaign_id}/statistics", response_model=dict)
async def campaign_statistics(
    campaign_id: UUID, actor=Depends(identity), db=Depends(get_db)
):
    await authorize(db, *actor, "campaigns:analytics")
    result = await update_stats(db, actor[0], campaign_id)
    await db.commit()
    return result


@router.post("/workflows", response_model=dict, status_code=201)
async def workflow_create(
    data: WorkflowInput, actor=Depends(identity), db=Depends(get_db)
):
    row = await save_workflow(db, *actor, data)
    await db.commit()
    return {
        "id": row.id,
        "name": row.name,
        "enabled": row.enabled,
        "version": row.version,
    }


@router.put("/workflows/{workflow_id}", response_model=dict)
async def workflow_update(
    workflow_id: UUID, data: WorkflowInput, actor=Depends(identity), db=Depends(get_db)
):
    row = await save_workflow(db, *actor, data, workflow_id)
    await db.commit()
    return {
        "id": row.id,
        "name": row.name,
        "enabled": row.enabled,
        "version": row.version,
    }


@router.patch("/workflows/{workflow_id}/enabled", response_model=dict)
async def workflow_enabled(
    workflow_id: UUID, data: ToggleInput, actor=Depends(identity), db=Depends(get_db)
):
    row = await toggle_workflow(db, *actor, workflow_id, data.enabled)
    await db.commit()
    return {"id": row.id, "enabled": row.enabled, "version": row.version}


@router.get("/workflows", response_model=Page)
async def workflows(
    enabled: bool | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    actor=Depends(identity),
    db=Depends(get_db),
):
    await authorize(db, *actor, "automation:read")
    query = select(Workflow).where(Workflow.tenant_id == actor[0])
    if enabled is not None:
        query = query.where(Workflow.enabled == enabled)
    return await page(
        db,
        Workflow,
        query.order_by(Workflow.created_at.desc(), Workflow.id),
        limit,
        offset,
        lambda row: {
            "id": row.id,
            "name": row.name,
            "version": row.version,
            "enabled": row.enabled,
        },
    )


@router.get("/workflows/{workflow_id}", response_model=dict)
async def workflow_detail(
    workflow_id: UUID, actor=Depends(identity), db=Depends(get_db)
):
    await authorize(db, *actor, "automation:read")
    row = await owned(db, Workflow, actor[0], workflow_id)
    revision = await db.scalar(
        select(WorkflowRevision).where(
            WorkflowRevision.tenant_id == actor[0],
            WorkflowRevision.workflow_id == row.id,
            WorkflowRevision.version == row.version,
        )
    )
    return {
        "id": row.id,
        "enabled": row.enabled,
        "version": row.version,
        "definition": revision.definition if revision else None,
    }


@router.get("/workflows/{workflow_id}/executions", response_model=Page)
async def workflow_executions(
    workflow_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    actor=Depends(identity),
    db=Depends(get_db),
):
    await authorize(db, *actor, "automation:read")
    await owned(db, Workflow, actor[0], workflow_id)
    query = (
        select(ExecutionLog)
        .where(
            ExecutionLog.tenant_id == actor[0], ExecutionLog.workflow_id == workflow_id
        )
        .order_by(ExecutionLog.created_at.desc(), ExecutionLog.id)
    )
    result = await page(
        db,
        ExecutionLog,
        query,
        limit,
        offset,
        lambda r: {
            "id": r.id,
            "event_id": r.event_id,
            "status": r.status,
            "version": r.workflow_version,
            "attempts": r.attempts,
            "error_code": r.error_code,
        },
    )
    execution_ids = [str(item["id"]) for item in result["items"]]
    if execution_ids:
        jobs = (await db.scalars(select(OperationJob).where(
            OperationJob.tenant_id == actor[0],
            OperationJob.kind == "automation",
            OperationJob.payload["execution_id"].astext.in_(execution_ids),
        ).order_by(OperationJob.created_at.desc()))).all()
        by_execution = {}
        for job in jobs:
            by_execution.setdefault(job.payload["execution_id"], job.id)
        for item in result["items"]:
            item["job_id"] = by_execution.get(str(item["id"]))
    return result



@router.get("/providers", response_model=list[dict])
async def providers(actor=Depends(identity), db=Depends(get_db)):
    await authorize(db, *actor, "integrations:read")
    return [
        {
            "provider": name,
            "capabilities": sorted(a.capabilities),
            "live_verified": False,
        }
        for name, a in adapters.items()
    ]


@router.post("/integrations/{integration_id}/authorize", response_model=dict)
async def oauth_start(
    integration_id: UUID, actor=Depends(identity), db=Depends(get_db)
):
    result = await start_oauth(db, *actor, integration_id)
    await db.commit()
    return result


@router.post("/integrations/{integration_id}/callback", response_model=dict)
async def oauth_callback(
    integration_id: UUID,
    data: OAuthCallback,
    actor=Depends(identity),
    db=Depends(get_db),
):
    result = await finish_oauth(db, *actor, integration_id, data)
    await db.commit()
    return result


@router.post("/integrations/{integration_id}/disconnect", response_model=dict)
async def integration_disconnect(
    integration_id: UUID, actor=Depends(identity), db=Depends(get_db)
):
    result = await disconnect(db, *actor, integration_id)
    await db.commit()
    return result


@router.get("/integrations/{integration_id}/status", response_model=dict)
async def integration_status(
    integration_id: UUID, actor=Depends(identity), db=Depends(get_db)
):
    await authorize(db, *actor, "integrations:read")
    row = await owned(db, Integration, actor[0], integration_id)
    token = await db.scalar(
        select(OAuthToken)
        .where(OAuthToken.tenant_id == actor[0], OAuthToken.integration_id == row.id)
        .order_by(OAuthToken.created_at.desc())
        .limit(1)
    )
    return {
        "id": row.id,
        "status": row.status.value,
        "capabilities": sorted(adapter_for(row).capabilities),
        "expires_at": token.expires_at if token else None,
        "expired": token is None
        or token.expires_at is None
        or token.expires_at <= now(),
    }


@router.post("/integrations/{integration_id}/refresh", response_model=dict)
async def integration_refresh(
    integration_id: UUID, actor=Depends(identity), db=Depends(get_db)
):
    await authorize(db, *actor, "integrations:write")
    row = await owned(db, Integration, actor[0], integration_id)
    await access_token(db, actor[0], row)
    await db.commit()
    return {"status": "credentials_valid"}


@router.post(
    "/integrations/{integration_id}/sync", response_model=JobResponse, status_code=202
)
async def integration_sync(
    integration_id: UUID,
    cursor: str | None = Query(None, max_length=1000),
    key=Depends(idempotency_key),
    actor=Depends(identity),
    db=Depends(get_db),
):
    job = await request_sync(db, *actor, integration_id, key, cursor)
    await db.commit()
    return public_job(job)


@router.post("/ai/requests", response_model=JobResponse, status_code=202)
async def ai_request(
    data: AIRequest,
    key=Depends(idempotency_key),
    actor=Depends(identity),
    db=Depends(get_db),
):
    job = await request_ai(db, *actor, data.capability, data.entity_id, key)
    await db.commit()
    return public_job(job)


from app.schemas.operations import AIBatchRequest


@router.post("/ai/batches", response_model=list[JobResponse], status_code=202)
async def ai_batch(
    data: AIBatchRequest,
    key=Depends(idempotency_key),
    actor=Depends(identity),
    db=Depends(get_db),
):
    from app.services.crm.common import enqueue

    batch, created = await enqueue(
        db, *actor, "ai_batch", "ai-batch:" + key, data.model_dump(mode="json")
    )
    if not created:
        jobs = [
            await owned(db, OperationJob, actor[0], UUID(value))
            for value in batch.result["job_ids"]
        ]
        for request in data.requests:
            from app.services.crm.ai import CAPABILITIES

            await authorize(db, *actor, CAPABILITIES[request.capability][1])
        return [public_job(job) for job in jobs]
    jobs = []
    for index, request in enumerate(data.requests):
        jobs.append(
            await request_ai(
                db, *actor, request.capability, request.entity_id, f"{key}:{index}"
            )
        )
    batch.status, batch.result = "completed", {"job_ids": [str(job.id) for job in jobs]}
    await db.commit()
    return [public_job(job) for job in jobs]


@router.get("/proposals/{proposal_id}", response_model=dict)
async def proposal_detail(
    proposal_id: UUID, actor=Depends(identity), db=Depends(get_db)
):
    from app.models import Proposal

    await authorize(db, *actor, "deals:read")
    row = await owned(db, Proposal, actor[0], proposal_id)
    return {
        "id": row.id,
        "deal_id": row.deal_id,
        "title": row.title,
        "status": row.status,
        "body": row.executive_summary,
        "version": row.version,
        "is_ai_generated": row.is_ai_generated,
    }


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def job_status(job_id: UUID, actor=Depends(identity), db=Depends(get_db)):
    row = await owned(db, OperationJob, actor[0], job_id)
    from app.services.crm.jobs import JOB_PERMISSIONS

    await authorize(db, *actor, JOB_PERMISSIONS.get(row.kind, "ai:chat"))
    if row.actor_id != actor[1]:
        await authorize(db, *actor, "audit:logs")
    return public_job(row)


@router.get("/jobs", response_model=Page)
async def jobs(
    kind: Literal[
        "ai", "ai_hook", "sync", "automation", "campaign_send", "message_send"
    ]
    | None = None,
    state: Literal[
        "pending",
        "running",
        "retry",
        "completed",
        "failed",
        "unknown",
        "awaiting_approval",
        "cancelled",
    ]
    | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    actor=Depends(identity),
    db=Depends(get_db),
):
    from app.services.crm.jobs import JOB_PERMISSIONS
    from app.core.rbac import get_role_permissions
    from app.models import Membership
    from sqlalchemy import or_

    member = await db.scalar(
        select(Membership).where(
            Membership.tenant_id == actor[0], Membership.user_id == actor[1]
        )
    )
    permissions = get_role_permissions(member.role)
    kinds = [
        name
        for name, perm in {**JOB_PERMISSIONS, "ai_hook": "ai:chat"}.items()
        if perm in permissions
    ]
    if kind and kind not in kinds:
        raise HTTPException(403, "Operation permission required")
    query = select(OperationJob).where(
        OperationJob.tenant_id == actor[0],
        OperationJob.kind.in_([kind] if kind else kinds),
    )
    if "audit:logs" not in permissions:
        query = query.where(
            or_(OperationJob.actor_id == actor[1], OperationJob.kind == "ai_hook")
        )
    if state:
        query = query.where(OperationJob.status == state)
    return await page(
        db,
        OperationJob,
        query.order_by(OperationJob.created_at.desc(), OperationJob.id),
        limit,
        offset,
        public_job,
    )


@router.post("/jobs/{job_id}/approve", response_model=JobResponse, status_code=202)
async def approve_ai_hook(job_id: UUID, actor=Depends(identity), db=Depends(get_db)):
    hook = await owned(db, OperationJob, actor[0], job_id, True)
    if hook.kind != "ai_hook" or hook.status not in {"awaiting_approval", "completed"}:
        raise HTTPException(409, "This job is not an AI suggestion awaiting approval")
    job = await request_ai(
        db,
        *actor,
        hook.payload["capability"],
        UUID(hook.payload["entity_id"]),
        "hook:" + str(hook.id),
    )
    hook.status, hook.result = "completed", {"job_id": str(job.id)}
    await db.commit()
    return public_job(job)


@router.post("/jobs/{job_id}/retry", response_model=JobResponse, status_code=202)
async def job_retry(job_id: UUID, actor=Depends(identity), db=Depends(get_db)):
    from app.services.crm.jobs import JOB_PERMISSIONS

    row = await owned(db, OperationJob, actor[0], job_id, True)
    await authorize(db, *actor, JOB_PERMISSIONS.get(row.kind, "audit:logs"))
    if (
        row.actor_id != actor[1]
        or row.kind not in {"automation", "sync"}
        or row.status != "failed"
        or row.attempts >= 3
    ):
        raise HTTPException(409, "This operation cannot be safely retried")
    row.status, row.available_at = "pending", now()
    await db.commit()
    return public_job(row)


@router.post("/events/{event_id}/retry", response_model=dict, status_code=202)
async def event_retry(event_id: UUID, actor=Depends(identity), db=Depends(get_db)):
    await authorize(db, *actor, "audit:logs")
    event = await owned(db, DomainEvent, actor[0], event_id, True)
    event.published_at = None
    audit(db, *actor, "event.retry_requested", "domain_event", event.id)
    await db.commit()
    return {"id": event.id, "status": "queued"}


@router.get("/analytics/{view}", response_model=dict)
async def analytics_view(
    view: Literal["dashboard", "pipeline", "conversion", "campaigns", "activity", "ai"],
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
    actor=Depends(identity),
    db=Depends(get_db),
):
    if start and end and start >= end:
        raise HTTPException(422, "Invalid date range")
    return await analytics(db, *actor, view, start, end)


@router.get("/search", response_model=Page)
async def global_search(
    q: str = Query(min_length=1, max_length=500),
    entity: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=900),
    actor=Depends(identity),
    db=Depends(get_db),
):
    from app.core.search import PostgresSearch
    from app.core.rbac import get_role_permissions
    from app.services.crm.customer import PERMISSIONS
    from app.models import Membership

    membership = await db.scalar(
        select(Membership).where(
            Membership.tenant_id == actor[0], Membership.user_id == actor[1]
        )
    )
    perms = get_role_permissions(membership.role)
    search = PostgresSearch(db)
    if entity and entity not in search.entities:
        raise HTTPException(422, "Unknown search entity")
    results = []
    for name in [entity] if entity else search.entities:
        permission = "ai:chat" if name == "agents" else PERMISSIONS[name]
        if permission not in perms:
            if entity:
                raise HTTPException(403, "Search permission required")
            continue
        results.extend(await search.search(actor[0], name, q, 100))
    results.sort(key=lambda row: (-row["rank"], row["entity"], row["id"]))
    return {
        "items": results[offset : offset + limit],
        "total": len(results),
        "limit": limit,
        "offset": offset,
    }


@router.post("/activities", response_model=dict, status_code=201)
async def activity_create(
    data: ActivityInput, actor=Depends(identity), db=Depends(get_db)
):
    await authorize(db, *actor, "tasks:write")
    await relations(db, actor[0], data.model_dump())
    from app.models import ActivityTypeEnum

    row = Activity(
        tenant_id=actor[0],
        user_id=actor[1],
        type=ActivityTypeEnum.MEETING,
        **data.model_dump(),
    )
    db.add(row)
    await db.commit()
    return {"id": row.id, "subject": row.subject, "created_at": row.created_at}


from app.schemas.operations import ToolInput


@router.post("/tools/{name}", response_model=dict)
async def crm_tool(
    name: Literal[
        "search_leads",
        "get_customer",
        "get_pipeline",
        "create_task",
        "update_lead",
        "create_note",
        "draft_email",
    ],
    data: ToolInput,
    key=Depends(idempotency_key),
    actor=Depends(identity),
    db=Depends(get_db),
):
    from app.services.crm.tools import execute_tool

    result = await execute_tool(db, *actor, name, data.arguments, key)
    await db.commit()
    return result
