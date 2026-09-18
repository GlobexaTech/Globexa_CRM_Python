"""Tenant-scoped API for executions, independent human approvals and retained memory."""

from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from app.api.v1.operations import identity, idempotency_key, page
from app.core.database import get_db
from app.core.rbac import get_role_permissions
from app.models import AgentExecution, ApprovalRequest, AgentMemory
from app.schemas.operations import Page
from app.schemas.workforce import (
    ExecutionInput,
    ExecutionResponse,
    ExecutionDetail,
    ApprovalResponse,
    ApprovalDecision,
    MemoryInput,
    MemoryResponse,
)
from app.services.ai.agent import (
    AGENTS,
    request_execution,
    visible_execution,
    cancel_execution,
    retry_execution,
)
from app.services.ai.approval import decide, request_approval
from app.services.ai.memory import purge_expired
from app.services.crm.common import authorize, owned, audit, now

router = APIRouter(prefix="/workforce", tags=["AI workforce"])


async def scoped(db, actor, model, actor_field):
    member = await authorize(db, *actor, "ai:chat")
    query = select(model).where(model.tenant_id == actor[0])
    if "ai:approve" not in get_role_permissions(member.role):
        query = query.where(actor_field == actor[1])
    return query


@router.get("/agents", response_model=dict)
async def agents(actor=Depends(identity), db=Depends(get_db)):
    member = await authorize(db, *actor, "ai:chat")
    from app.services.ai.workforce_tools import TOOL_SPECS

    permissions = get_role_permissions(member.role)
    return {
        "items": [
            {
                "name": name,
                "label": spec["label"],
                "tools": sorted(
                    tool for tool in spec["tools"] if TOOL_SPECS[tool][0] in permissions
                ),
            }
            for name, spec in AGENTS.items()
        ]
    }


@router.post("/executions", response_model=ExecutionResponse, status_code=202)
async def create(
    data: ExecutionInput, actor=Depends(identity), db=Depends(get_db), key=Depends(idempotency_key)
):
    row = await request_execution(db, *actor, data, key)
    await db.commit()
    return row


@router.get("/executions", response_model=Page)
async def executions(
    agent_name: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    actor=Depends(identity),
    db=Depends(get_db),
):
    query = await scoped(db, actor, AgentExecution, AgentExecution.actor_id)
    if agent_name:
        query = query.where(AgentExecution.agent_name == agent_name)
    if entity_type:
        query = query.where(AgentExecution.task["context"]["entity_type"].astext == entity_type)
    if entity_id:
        query = query.where(AgentExecution.task["context"]["entity_id"].astext == str(entity_id))
    return await page(
        db,
        AgentExecution,
        query.order_by(AgentExecution.created_at.desc()),
        limit,
        offset,
        lambda row: ExecutionResponse.model_validate(row).model_dump(mode="json"),
    )


@router.get("/executions/{execution_id}", response_model=ExecutionDetail)
async def detail(execution_id: UUID, actor=Depends(identity), db=Depends(get_db)):
    row = await visible_execution(db, *actor, execution_id)
    children = (
        await db.scalars(
            select(AgentExecution)
            .where(AgentExecution.tenant_id == actor[0], AgentExecution.parent_id == row.id)
            .order_by(AgentExecution.created_at)
        )
    ).all()
    return {
        **ExecutionResponse.model_validate(row).model_dump(),
        "children": [ExecutionResponse.model_validate(child) for child in children],
    }


@router.post("/executions/{execution_id}/cancel", response_model=ExecutionResponse)
async def cancel(execution_id: UUID, actor=Depends(identity), db=Depends(get_db)):
    row = await cancel_execution(db, *actor, execution_id)
    await db.commit()
    return row


@router.post("/executions/{execution_id}/retry", response_model=ExecutionResponse, status_code=202)
async def retry(
    execution_id: UUID, actor=Depends(identity), db=Depends(get_db), key=Depends(idempotency_key)
):
    row = await retry_execution(db, *actor, execution_id, key)
    await db.commit()
    return row


@router.get("/approvals", response_model=Page)
async def approvals(
    status: Literal["pending", "approved", "rejected", "expired", "executed", "failed"]
    | None = None,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    actor=Depends(identity),
    db=Depends(get_db),
):
    query = await scoped(db, actor, ApprovalRequest, ApprovalRequest.requesting_user_id)
    # Expiry becomes durable when the user inspects the queue, not a fabricated UI state.
    expired = (
        await db.scalars(
            query.where(
                ApprovalRequest.status.in_(["pending", "approved"]),
                ApprovalRequest.expires_at <= now(),
                ApprovalRequest.execution_result.is_(None),
            )
        )
    ).all()
    for row in expired:
        row.status = "expired"
    if expired:
        await db.commit()
    if status:
        query = query.where(ApprovalRequest.status == status)
    return await page(
        db,
        ApprovalRequest,
        query.order_by(ApprovalRequest.created_at.desc()),
        limit,
        offset,
        lambda row: ApprovalResponse.model_validate(row).model_dump(mode="json"),
    )


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalResponse)
async def decision(
    approval_id: UUID, data: ApprovalDecision, actor=Depends(identity), db=Depends(get_db)
):
    row = await decide(db, *actor, approval_id, data)
    await db.commit()
    return row


@router.get("/memory", response_model=Page)
async def memories(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    actor=Depends(identity),
    db=Depends(get_db),
):
    query = await scoped(db, actor, AgentMemory, AgentMemory.actor_id)
    await purge_expired(db, actor[0])
    await db.commit()
    return await page(
        db,
        AgentMemory,
        query.order_by(AgentMemory.created_at.desc()),
        limit,
        offset,
        lambda row: MemoryResponse.model_validate(row).model_dump(mode="json"),
    )


@router.post("/memory", response_model=ApprovalResponse, status_code=202)
async def remember(
    data: MemoryInput, actor=Depends(identity), db=Depends(get_db), key=Depends(idempotency_key)
):
    row = await request_approval(
        db, *actor, data.agent_name, "remember", data.model_dump(mode="json"), key
    )
    await db.commit()
    return row


@router.delete("/memory/{memory_id}", status_code=204)
async def forget(memory_id: UUID, actor=Depends(identity), db=Depends(get_db)):
    member = await authorize(db, *actor, "ai:chat")
    row = await owned(db, AgentMemory, actor[0], memory_id, True)
    if row.actor_id != actor[1] and "ai:approve" not in get_role_permissions(member.role):
        raise HTTPException(404, "Memory not found")
    await db.delete(row)
    audit(db, *actor, "memory.deleted", "agent_memory", memory_id)
    await db.commit()
