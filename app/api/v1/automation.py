"""Versioned automation controls with tenant-scoped, bounded public contracts."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from app.api.v1.operations import identity, idempotency_key, page
from app.core.database import get_db
from app.models import (
    Automation,
    AutomationExecution,
    AutomationStepExecution,
    AutomationVersion,
    AutomationPolicy,
    AutomationNotification,
)
from app.schemas.automation import AutomationInput, ExecuteInput, SimulateInput, Limits, TRIGGERS
from app.schemas.operations import Page
from app.services.automation import service, engine
from app.services.automation.validation import validate_publish, policy
from app.services.automation.actions import ACTIONS, schema_for
from app.services.automation.intelligence import analytics, inspect_entity
from app.services.crm.common import authorize, owned, audit, serial_key, now

router = APIRouter(prefix="/automation", tags=["Advanced automation"])


def public(row):
    # Models contain no provider credentials. Only mapped columns are serialized;
    # ORM internals and relationships never enter the response.
    return jsonable_encoder(
        {
            column.key: getattr(row, column.key)
            for column in row.__table__.columns
            if column.key != "tenant_id"
        }
    )


@router.get("/catalog", response_model=dict)
async def catalog(actor=Depends(identity), db=Depends(get_db)):
    await authorize(db, *actor, "automation:read")
    return {
        "triggers": sorted(TRIGGERS),
        "actions": {name: schema_for(name).model_json_schema() for name in sorted(ACTIONS)},
        "node_types": [
            "condition",
            "action",
            "delay",
            "ai",
            "ai_decision",
            "approval",
            "intelligence",
        ],
        "limits": (await policy(db, actor[0])).model_dump(),
    }


@router.get("/policy", response_model=Limits)
async def get_policy(actor=Depends(identity), db=Depends(get_db)):
    await authorize(db, *actor, "automation:read")
    return await policy(db, actor[0])


@router.put("/policy", response_model=Limits)
async def set_policy(data: Limits, actor=Depends(identity), db=Depends(get_db)):
    await authorize(db, *actor, "tenant:settings")
    await authorize(db, *actor, "automation:write")
    await serial_key(db, actor[0], "automation-policy")
    row = await db.scalar(
        select(AutomationPolicy).where(AutomationPolicy.tenant_id == actor[0]).with_for_update()
    )
    if row is None:
        row = AutomationPolicy(tenant_id=actor[0], updated_by=actor[1])
        db.add(row)
    row.limits, row.updated_by = data.model_dump(), actor[1]
    audit(db, *actor, "automation.policy.updated", "automation_policy", row.id)
    await db.commit()
    return data


@router.get("/analytics", response_model=dict)
async def metrics(automation_id: UUID | None = None, actor=Depends(identity), db=Depends(get_db)):
    return await analytics(db, *actor, automation_id)


@router.get("/intelligence/{kind}/{entity_type}/{entity_id}", response_model=dict)
async def intelligence(
    kind: Literal["lead", "deal", "customer", "campaign", "next_best_action"],
    entity_type: Literal["lead", "deal", "contact", "campaign"],
    entity_id: UUID,
    actor=Depends(identity),
    db=Depends(get_db),
):
    await authorize(db, *actor, "automation:read")
    return await inspect_entity(db, *actor, kind, entity_type, entity_id)


@router.get("/notifications", response_model=Page)
async def notifications(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    actor=Depends(identity),
    db=Depends(get_db),
):
    await authorize(db, *actor, "automation:read")
    query = select(AutomationNotification).where(
        AutomationNotification.tenant_id == actor[0], AutomationNotification.user_id == actor[1]
    )
    return await page(
        db,
        AutomationNotification,
        query.order_by(AutomationNotification.created_at.desc()),
        limit,
        offset,
        public,
    )


@router.post("/notifications/{notification_id}/read", response_model=dict)
async def read_notification(notification_id: UUID, actor=Depends(identity), db=Depends(get_db)):
    await authorize(db, *actor, "automation:read")
    row = await owned(db, AutomationNotification, actor[0], notification_id, True)
    if row.user_id != actor[1]:
        raise HTTPException(404, "Notification not found")
    row.read_at = now()
    await db.commit()
    return public(row)


@router.get("/executions", response_model=Page)
async def executions(
    automation_id: UUID | None = None,
    state: Literal[
        "QUEUED", "RUNNING", "WAITING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED", "EXPIRED"
    ]
    | None = None,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    actor=Depends(identity),
    db=Depends(get_db),
):
    await authorize(db, *actor, "automation:read")
    query = select(AutomationExecution).where(AutomationExecution.tenant_id == actor[0])
    if automation_id:
        query = query.where(AutomationExecution.automation_id == automation_id)
    if state:
        query = query.where(AutomationExecution.state == state)
    return await page(
        db,
        AutomationExecution,
        query.order_by(AutomationExecution.created_at.desc(), AutomationExecution.id),
        limit,
        offset,
        public,
    )


@router.get("/executions/{execution_id}", response_model=dict)
async def execution_detail(execution_id: UUID, actor=Depends(identity), db=Depends(get_db)):
    await authorize(db, *actor, "automation:read")
    row = await owned(db, AutomationExecution, actor[0], execution_id)
    steps = (
        await db.scalars(
            select(AutomationStepExecution)
            .where(
                AutomationStepExecution.tenant_id == actor[0],
                AutomationStepExecution.execution_id == row.id,
            )
            .order_by(AutomationStepExecution.created_at, AutomationStepExecution.id)
            .limit(100)
        )
    ).all()
    return {**public(row), "steps": [public(step) for step in steps]}


@router.post("/executions/{execution_id}/{action}", response_model=dict)
async def execution_transition(
    execution_id: UUID,
    action: Literal["pause", "resume", "cancel", "retry"],
    actor=Depends(identity),
    db=Depends(get_db),
):
    row = await engine.transition_execution(db, *actor, execution_id, action)
    await db.commit()
    return public(row)


@router.get("/workflows", response_model=Page)
async def workflows(
    status: Literal["DRAFT", "ACTIVE", "PAUSED", "DISABLED", "ARCHIVED"] | None = None,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    actor=Depends(identity),
    db=Depends(get_db),
):
    await authorize(db, *actor, "automation:read")
    query = select(Automation).where(Automation.tenant_id == actor[0])
    if status:
        query = query.where(Automation.status == status)
    return await page(
        db,
        Automation,
        query.order_by(Automation.updated_at.desc(), Automation.id),
        limit,
        offset,
        public,
    )


@router.post("/workflows", response_model=dict, status_code=201)
async def create(data: AutomationInput, actor=Depends(identity), db=Depends(get_db)):
    row = await service.save(db, *actor, data)
    await db.commit()
    return public(row)


@router.get("/workflows/{automation_id}", response_model=dict)
async def detail(automation_id: UUID, actor=Depends(identity), db=Depends(get_db)):
    await authorize(db, *actor, "automation:read")
    return public(await owned(db, Automation, actor[0], automation_id))


@router.put("/workflows/{automation_id}", response_model=dict)
async def update(
    automation_id: UUID, data: AutomationInput, actor=Depends(identity), db=Depends(get_db)
):
    row = await service.save(db, *actor, data, automation_id)
    await db.commit()
    return public(row)


@router.get("/workflows/{automation_id}/versions", response_model=Page)
async def versions(
    automation_id: UUID,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    actor=Depends(identity),
    db=Depends(get_db),
):
    await authorize(db, *actor, "automation:read")
    await owned(db, Automation, actor[0], automation_id)
    query = select(AutomationVersion).where(
        AutomationVersion.tenant_id == actor[0], AutomationVersion.automation_id == automation_id
    )
    return await page(
        db,
        AutomationVersion,
        query.order_by(AutomationVersion.number.desc()),
        limit,
        offset,
        public,
    )


@router.post("/workflows/{automation_id}/validate", response_model=dict)
async def validate(automation_id: UUID, actor=Depends(identity), db=Depends(get_db)):
    await authorize(db, *actor, "automation:write")
    row = await owned(db, Automation, actor[0], automation_id)
    try:
        definition = await validate_publish(db, *actor, row.draft)
        from app.services.automation.validation import validate_chains
        await validate_chains(db, actor[0], row.id, definition)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {"valid": True, "draft": True}


@router.post("/workflows/{automation_id}/simulate", response_model=dict)
async def simulate(
    automation_id: UUID, data: SimulateInput, actor=Depends(identity), db=Depends(get_db)
):
    await authorize(db, *actor, "automation:write")
    row = await owned(db, Automation, actor[0], automation_id)
    from app.services.ai.safety import safe_data

    safe_data(data.context)
    try:
        result = (
            await service.simulate_with_model(db, *actor, row.draft, data.context)
            if data.use_model
            else service.simulate(row.draft, data.context)
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except RuntimeError:
        raise HTTPException(503, "Configured model is unavailable") from None
    audit(db, *actor, "automation.simulated", "automation", row.id)
    await db.commit()
    return result


@router.post("/workflows/{automation_id}/execute", response_model=dict, status_code=202)
async def execute(
    automation_id: UUID,
    data: ExecuteInput,
    key=Depends(idempotency_key),
    actor=Depends(identity),
    db=Depends(get_db),
):
    row = await engine.request_execution(
        db, *actor, automation_id, data.model_dump(mode="json"), "api:" + key
    )
    await db.commit()
    return public(row)


@router.post("/workflows/{automation_id}/{action}", response_model=dict)
async def workflow_transition(
    automation_id: UUID,
    action: Literal["publish", "pause", "resume", "disable", "archive", "clone"],
    actor=Depends(identity),
    db=Depends(get_db),
):
    try:
        if action == "publish":
            row = await service.publish(db, *actor, automation_id)
        elif action == "clone":
            row = await service.clone(db, *actor, automation_id)
        else:
            row = await service.transition(db, *actor, automation_id, action)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    await db.commit()
    return public(row)
