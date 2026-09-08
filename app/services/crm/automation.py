"""Bounded declarative workflows; actions use the same permission-checked services as tools."""

from uuid import UUID
from sqlalchemy import select, delete
from fastapi import HTTPException
from app.models import (
    Workflow,
    Trigger,
    Condition,
    Action,
    ExecutionLog,
    WorkflowRevision,
    DomainEvent,
    Lead,
    Deal,
    Task,
    Note,
    Contact,
    Company,
    Stage,
    Membership,
)
from app.schemas import TaskCreate, NoteCreate, LeadUpdate, DealUpdate
from app.schemas.operations import WorkflowInput, MessageInput
from app.services.crm.common import owned, authorize, meter, audit, enqueue
from app.core.events import event_depth, publish_event
from app.core.input_security import contains_secrets

ACTION_PERMISSIONS = {
    "create_task": "tasks:write",
    "update_lead": "leads:write",
    "update_deal": "deals:write",
    "add_note": "notes:write",
    "send_email": "conversations:send",
    "assign_owner": "leads:assign",
    "invoke_ai": "ai:chat",
}
FIELDS = {
    "create_task": {
        "title",
        "description",
        "lead_id",
        "deal_id",
        "contact_id",
        "company_id",
        "due_date",
        "priority",
        "owner_id",
    },
    "add_note": {"content", "lead_id", "deal_id", "contact_id", "company_id"},
    "update_lead": {"entity_id", "title", "description", "status"},
    "update_deal": {"entity_id", "title", "description", "stage_id", "value"},
    "assign_owner": {"entity_id", "owner_id"},
    "send_email": {"conversation_id", "recipient", "body"},
    "invoke_ai": {"capability", "entity_id"},
}


async def save_workflow(db, tenant_id, actor_id, data, workflow_id=None):
    await authorize(db, tenant_id, actor_id, "automation:write")
    for action in data.actions:
        if set(action.arguments) - FIELDS[action.tool] or contains_secrets(
            action.arguments
        ):
            raise HTTPException(422, "Unsupported workflow arguments")
        await authorize(db, tenant_id, actor_id, ACTION_PERMISSIONS[action.tool])
    if workflow_id:
        row = await owned(db, Workflow, tenant_id, workflow_id, True)
        row.version += 1
        row.name, row.enabled, row.owner_id = data.name, False, actor_id
        for model in (Trigger, Condition, Action):
            await db.execute(
                delete(model).where(
                    model.tenant_id == tenant_id, model.workflow_id == row.id
                )
            )
    else:
        row = Workflow(
            tenant_id=tenant_id, owner_id=actor_id, name=data.name, enabled=False
        )
        db.add(row)
        await db.flush()
    db.add(Trigger(tenant_id=tenant_id, workflow_id=row.id, event_type=data.trigger))
    for condition in data.conditions:
        db.add(
            Condition(
                tenant_id=tenant_id,
                workflow_id=row.id,
                expression=condition.model_dump(),
            )
        )
    for position, action in enumerate(data.actions):
        db.add(
            Action(
                tenant_id=tenant_id,
                workflow_id=row.id,
                position=position,
                **action.model_dump(),
            )
        )
    db.add(
        WorkflowRevision(
            tenant_id=tenant_id,
            workflow_id=row.id,
            version=row.version,
            definition=data.model_dump(mode="json"),
        )
    )
    audit(db, tenant_id, actor_id, "workflow.changed", "workflow", row.id)
    await db.flush()
    return row


async def toggle_workflow(db, tenant_id, actor_id, workflow_id, enabled):
    await authorize(db, tenant_id, actor_id, "automation:write")
    row = await owned(db, Workflow, tenant_id, workflow_id, True)
    if enabled:
        if not row.owner_id:
            raise HTTPException(
                409, "Edit the legacy workflow to establish an accountable owner first"
            )
        await authorize(db, tenant_id, row.owner_id, "automation:write")
        from app.models import FeatureEntitlement

        rule = await db.scalar(
            select(FeatureEntitlement).where(
                FeatureEntitlement.tenant_id == tenant_id,
                FeatureEntitlement.feature_key == "automation",
                FeatureEntitlement.enabled.is_(True),
            )
        )
        if not rule:
            raise HTTPException(403, "Automation entitlement required")
    row.enabled = enabled
    audit(
        db,
        tenant_id,
        actor_id,
        "workflow.enabled" if enabled else "workflow.disabled",
        "workflow",
        row.id,
    )
    return row


async def relations(db, tenant_id, values):
    for field, model in {
        "lead_id": Lead,
        "deal_id": Deal,
        "contact_id": Contact,
        "company_id": Company,
    }.items():
        if values.get(field):
            await owned(db, model, tenant_id, values[field])
    if values.get("owner_id"):
        member = await db.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant_id,
                Membership.user_id == values["owner_id"],
            )
        )
        if not member:
            raise HTTPException(404, "Owner is not a tenant member")


async def perform_action(db, tenant_id, actor_id, tool, arguments, key):
    if (
        tool not in FIELDS
        or set(arguments) - FIELDS[tool]
        or contains_secrets(arguments)
    ):
        raise HTTPException(422, "Unapproved action or arguments")
    await authorize(db, tenant_id, actor_id, ACTION_PERMISSIONS[tool])
    if tool in {"create_task", "add_note"}:
        schema, model = (
            (TaskCreate, Task) if tool == "create_task" else (NoteCreate, Note)
        )
        values = schema.model_validate(arguments).model_dump()
        if tool == "create_task":
            values["owner_id"] = values.get("owner_id") or actor_id
        if not any(
            values.get(k) for k in ("lead_id", "deal_id", "contact_id", "company_id")
        ):
            raise HTTPException(422, "A customer relation is required")
        await relations(db, tenant_id, values)
        values["created_by_id" if tool == "create_task" else "author_id"] = actor_id
        row = model(tenant_id=tenant_id, **values)
        db.add(row)
        await db.flush()
        return {"id": str(row.id)}
    if tool in {"update_lead", "update_deal", "assign_owner"}:
        model = Deal if tool == "update_deal" else Lead
        row = await owned(db, model, tenant_id, UUID(arguments["entity_id"]), True)
        values = {k: v for k, v in arguments.items() if k != "entity_id"}
        if tool == "assign_owner":
            values["owner_id"] = UUID(values["owner_id"])
            await relations(db, tenant_id, values)
        else:
            values = (
                (DealUpdate if model is Deal else LeadUpdate)
                .model_validate(values)
                .model_dump(exclude_unset=True)
            )
        if values.get("stage_id"):
            stage = await owned(db, Stage, tenant_id, values["stage_id"])
            if stage.pipeline_id != row.pipeline_id:
                raise HTTPException(422, "Stage is outside the deal pipeline")
        for field, value in values.items():
            setattr(row, field, value)
        await db.flush()
        return {"id": str(row.id)}
    if tool == "send_email":
        from app.services.crm.conversations import queue_message

        data = MessageInput.model_validate(
            {k: v for k, v in arguments.items() if k != "conversation_id"}
        )
        job = await queue_message(
            db, tenant_id, actor_id, UUID(arguments["conversation_id"]), data, key
        )
    else:
        from app.services.crm.ai import request_ai

        job = await request_ai(
            db,
            tenant_id,
            actor_id,
            arguments["capability"],
            UUID(arguments["entity_id"]),
            key,
        )
    return {"job_id": str(job.id)}


async def trigger_workflows(db, event):
    if int(event.payload.get("_depth", 0)) >= 3:
        return
    rows = (
        await db.scalars(
            select(Workflow)
            .join(Trigger, Trigger.workflow_id == Workflow.id)
            .where(
                Workflow.tenant_id == event.tenant_id,
                Workflow.enabled.is_(True),
                Trigger.event_type == event.event_type,
            )
        )
    ).all()
    for row in rows:
        revision = await db.scalar(
            select(WorkflowRevision).where(
                WorkflowRevision.tenant_id == event.tenant_id,
                WorkflowRevision.workflow_id == row.id,
                WorkflowRevision.version == row.version,
            )
        )
        if not revision:
            continue
        existing = await db.scalar(
            select(ExecutionLog).where(
                ExecutionLog.tenant_id == event.tenant_id,
                ExecutionLog.workflow_id == row.id,
                ExecutionLog.event_id == event.id,
            )
        )
        if existing:
            continue
        log = ExecutionLog(
            tenant_id=event.tenant_id,
            workflow_id=row.id,
            event_id=event.id,
            workflow_version=row.version,
            snapshot=revision.definition,
        )
        db.add(log)
        await db.flush()
        await enqueue(
            db,
            event.tenant_id,
            row.owner_id,
            "automation",
            "workflow:" + str(log.id),
            {"execution_id": str(log.id)},
        )


async def execute_workflow(db, tenant_id, job):
    log = await owned(
        db, ExecutionLog, tenant_id, UUID(job.payload["execution_id"]), True
    )
    if log.status == "completed":
        return {"execution_id": str(log.id), "status": "completed"}
    workflow = await owned(db, Workflow, tenant_id, log.workflow_id)
    if not workflow.enabled or workflow.owner_id != job.actor_id:
        raise HTTPException(409, "Workflow disabled or owner changed")
    await authorize(db, tenant_id, job.actor_id, "automation:write")
    event = await owned(db, DomainEvent, tenant_id, log.event_id)
    definition = WorkflowInput.model_validate(log.snapshot)
    log.attempts += 1
    token = event_depth.set(int(event.payload.get("_depth", 0)) + 1)
    try:
        for condition in definition.conditions:
            value = event.payload.get(condition.field)
            target = condition.value
            result = {
                "eq": lambda: value == target,
                "ne": lambda: value != target,
                "gt": lambda: value is not None and value > target,
                "lt": lambda: value is not None and value < target,
            }[condition.operator]()
            if not result:
                log.status = "skipped"
                return {"status": "skipped"}
        await meter(db, tenant_id, job.actor_id, "automation")
        results = []
        for index, action in enumerate(definition.actions):
            args = {
                k: event.aggregate_id
                if v == "$event.id"
                else event.payload.get(v[7:])
                if isinstance(v, str) and v.startswith("$event.")
                else v
                for k, v in action.arguments.items()
            }
            results.append(
                await perform_action(
                    db,
                    tenant_id,
                    job.actor_id,
                    action.tool,
                    args,
                    f"workflow:{log.id}:{index}",
                )
            )
        log.status, log.error_code = "completed", None
        publish_event(
            db,
            tenant_id=tenant_id,
            actor_id=job.actor_id,
            event_type="automation.completed",
            aggregate_id=workflow.id,
            idempotency_key="workflow-complete:" + str(log.id),
        )
        return {"execution_id": str(log.id), "actions": results}
    finally:
        event_depth.reset(token)
