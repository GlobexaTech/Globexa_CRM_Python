"""Drafts can change; published versions and their normalized records cannot."""
from datetime import timedelta
from uuid import UUID
from sqlalchemy import select
from fastapi import HTTPException
from app.models import (Automation, AutomationVersion, AutomationTrigger, AutomationCondition,
    AutomationAction, AutomationVariable, AutomationCredentialReference, AutomationSchedule)
from app.services.crm.common import authorize, owned, audit, now
from app.services.ai.approval import fingerprint
from app.schemas.automation import AutomationInput, Definition
from app.services.automation.validation import validate_publish, validate_structure
from app.services.automation.scheduling import next_occurrence


async def save(db, tenant_id, actor_id, data, automation_id=None):
    await authorize(db, tenant_id, actor_id, "automation:write")
    from app.services.ai.safety import safe_data
    for node in data.definition.nodes: safe_data(node.arguments)
    safe_data(data.definition.variables)
    if automation_id:
        row = await owned(db, Automation, tenant_id, automation_id, True)
        if row.status == "ARCHIVED": raise HTTPException(409, "Archived automation is immutable; clone it")
        row.name, row.description, row.draft = data.name, data.description, data.definition.model_dump(mode="json")
    else:
        row = Automation(tenant_id=tenant_id, name=data.name, description=data.description,
                         owner_id=actor_id, draft=data.definition.model_dump(mode="json"))
        db.add(row)
    await db.flush()
    audit(db, tenant_id, actor_id, "automation.updated" if automation_id else "automation.created", "automation", row.id)
    return row


async def publish(db, tenant_id, actor_id, automation_id):
    await authorize(db, tenant_id, actor_id, "automation:write")
    row = await owned(db, Automation, tenant_id, automation_id, True)
    if row.status == "ARCHIVED": raise HTTPException(409, "Archived automation cannot publish")
    await validate_publish(db, tenant_id, actor_id, row.draft)
    definition = await validate_publish(db, tenant_id, row.owner_id, row.draft)
    row.version += 1
    version = AutomationVersion(tenant_id=tenant_id, automation_id=row.id, number=row.version,
        definition=definition.model_dump(mode="json"), digest=fingerprint(definition.model_dump(mode="json")), published_by=actor_id)
    db.add(version); await db.flush()
    db.add(AutomationTrigger(tenant_id=tenant_id, version_id=version.id, event_type=definition.trigger))
    for node in definition.nodes:
        if node.type == "condition":
            db.add(AutomationCondition(tenant_id=tenant_id, version_id=version.id, node_key=node.id, expression=node.condition))
        else:
            db.add(AutomationAction(tenant_id=tenant_id, version_id=version.id, node_key=node.id, kind=node.type, arguments=node.model_dump(mode="json")))
    for name, value in definition.variables.items():
        db.add(AutomationVariable(tenant_id=tenant_id, version_id=version.id, name=name, value={"value": value}))
    for name, integration_id in definition.credentials.items():
        db.add(AutomationCredentialReference(tenant_id=tenant_id, version_id=version.id, name=name, integration_id=integration_id))
    schedule = await db.scalar(select(AutomationSchedule).where(AutomationSchedule.tenant_id == tenant_id, AutomationSchedule.automation_id == row.id))
    if definition.schedule:
        config = definition.schedule.model_dump(mode="json")
        if not schedule:
            schedule = AutomationSchedule(tenant_id=tenant_id, automation_id=row.id)
            db.add(schedule)
        schedule.configuration, schedule.timezone, schedule.enabled = config, definition.schedule.timezone, True
        schedule.scheduled_at = next_occurrence(config, now())
    elif schedule: schedule.enabled = False
    row.status, row.updated_at = "ACTIVE", now()
    audit(db, tenant_id, actor_id, "automation.published", "automation_version", version.id)
    await db.flush()
    return row


async def transition(db, tenant_id, actor_id, automation_id, action):
    await authorize(db, tenant_id, actor_id, "automation:write")
    row = await owned(db, Automation, tenant_id, automation_id, True)
    allowed = {"pause": {"ACTIVE"}, "resume": {"PAUSED", "DISABLED"},
               "disable": {"DRAFT", "ACTIVE", "PAUSED"}, "archive": {"DRAFT", "ACTIVE", "PAUSED", "DISABLED"}}
    if action not in allowed or row.status not in allowed[action]: raise HTTPException(409, "Invalid automation transition")
    if action == "resume":
        version = await db.scalar(select(AutomationVersion).where(AutomationVersion.tenant_id == tenant_id, AutomationVersion.automation_id == row.id, AutomationVersion.number == row.version))
        if not version: raise HTTPException(409, "Publish a version before resuming")
        await authorize(db, tenant_id, row.owner_id, "automation:write")
    row.status = {"pause": "PAUSED", "resume": "ACTIVE", "disable": "DISABLED", "archive": "ARCHIVED"}[action]
    audit(db, tenant_id, actor_id, "automation." + row.status.lower(), "automation", row.id)
    return row


async def clone(db, tenant_id, actor_id, automation_id):
    await authorize(db, tenant_id, actor_id, "automation:write")
    row = await owned(db, Automation, tenant_id, automation_id)
    return await save(db, tenant_id, actor_id, AutomationInput(name=(row.name + " copy")[:255], description=row.description, definition=Definition.model_validate(row.draft)))


def simulate(definition, context):
    from app.services.automation.expressions import bounded_context, evaluate, render
    from app.services.automation.validation import successors
    from app.services.automation.actions import EXTERNAL
    definition = validate_structure(definition)
    bounded_context(context)
    context = {**context, "vars": definition.variables, "steps": {}}
    rows, current = [], definition.nodes[0].id
    nodes = {node.id: (index, node) for index, node in enumerate(definition.nodes)}
    while current:
        index, node = nodes[current]
        next_node, false_node, _ = successors(definition.nodes, index)
        result = {"node": current, "type": node.type, "action": node.action, "executed": False}
        if node.type in {"ai", "ai_decision"}:
            result.update(status="requires_live_model_execution", decision=None)
            rows.append(result)
            # Do not invent an AI decision to choose a branch in a side-effect-free test.
            return {"dry_run": True, "trigger": definition.trigger, "steps": rows, "remaining_nodes": [n.id for n in definition.nodes[index + 1:]], "blocked_on": current}
        try:
            result["arguments"] = render(node.arguments, context)
            if node.type == "condition":
                result["matched"] = evaluate(node.condition, context, context.get("before"))
                next_node = next_node if result["matched"] else false_node
            result["requires_approval"] = node.type == "approval" or node.action in EXTERNAL or "steps." in str(node.arguments)
        except HTTPException:
            result["error"] = "missing_test_variable"
            rows.append(result)
            return {"dry_run": True, "trigger": definition.trigger, "steps": rows, "blocked_on": current}
        rows.append(result); context["steps"][current] = result; current = next_node
    return {"dry_run": True, "trigger": definition.trigger, "steps": rows, "remaining_nodes": []}
