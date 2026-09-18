"""Drafts can change; published versions and their normalized records cannot."""

from sqlalchemy import select, func
from fastapi import HTTPException
from app.models import (
    Automation,
    AutomationVersion,
    AutomationTrigger,
    AutomationCondition,
    AutomationAction,
    AutomationVariable,
    AutomationCredentialReference,
    AutomationSchedule,
)
from app.services.crm.common import authorize, owned, audit, now, serial_key
from app.services.ai.approval import fingerprint
from app.schemas.automation import AutomationInput, Definition
from app.services.automation.validation import validate_publish, validate_structure, validate_chains
from app.services.automation.scheduling import next_occurrence


async def save(db, tenant_id, actor_id, data, automation_id=None):
    await authorize(db, tenant_id, actor_id, "automation:write")
    from app.services.ai.safety import safe_data

    for node in data.definition.nodes:
        safe_data(node.arguments)
    safe_data(data.definition.variables)
    if automation_id:
        row = await owned(db, Automation, tenant_id, automation_id, True)
        if row.status == "ARCHIVED":
            raise HTTPException(409, "Archived automation is immutable; clone it")
        row.name, row.description, row.draft = (
            data.name,
            data.description,
            data.definition.model_dump(mode="json"),
        )
    else:
        row = Automation(
            tenant_id=tenant_id,
            name=data.name,
            description=data.description,
            owner_id=actor_id,
            draft=data.definition.model_dump(mode="json"),
        )
        db.add(row)
    await db.flush()
    audit(
        db,
        tenant_id,
        actor_id,
        "automation.updated" if automation_id else "automation.created",
        "automation",
        row.id,
    )
    return row


async def check_active_capacity(db, tenant_id, automation_id, trigger):
    # The outbox consumer processes at most 100 matches per event. Admission uses
    # the same tenant lock for publication and resumption, so no match is dropped.
    await serial_key(db, tenant_id, "automation-active-capacity")
    count = await db.scalar(
        select(func.count())
        .select_from(Automation)
        .join(AutomationVersion, AutomationVersion.automation_id == Automation.id)
        .join(AutomationTrigger, AutomationTrigger.version_id == AutomationVersion.id)
        .where(
            Automation.tenant_id == tenant_id,
            Automation.id != automation_id,
            Automation.status == "ACTIVE",
            AutomationVersion.number == Automation.version,
            AutomationTrigger.event_type == trigger,
        )
    )
    if count >= 100:
        raise HTTPException(429, "At most 100 active automations per trigger are supported")


async def publish(db, tenant_id, actor_id, automation_id):
    await authorize(db, tenant_id, actor_id, "automation:write")
    row = await owned(db, Automation, tenant_id, automation_id, True)
    if row.status == "ARCHIVED":
        raise HTTPException(409, "Archived automation cannot publish")
    await validate_publish(db, tenant_id, actor_id, row.draft)
    definition = await validate_publish(db, tenant_id, row.owner_id, row.draft)
    await check_active_capacity(db, tenant_id, row.id, definition.trigger)
    await validate_chains(db, tenant_id, row.id, definition)
    row.version += 1
    version = AutomationVersion(
        tenant_id=tenant_id,
        automation_id=row.id,
        number=row.version,
        definition=definition.model_dump(mode="json"),
        digest=fingerprint(definition.model_dump(mode="json")),
        published_by=actor_id,
    )
    db.add(version)
    await db.flush()
    db.add(
        AutomationTrigger(tenant_id=tenant_id, version_id=version.id, event_type=definition.trigger)
    )
    for node in definition.nodes:
        if node.type == "condition":
            db.add(
                AutomationCondition(
                    tenant_id=tenant_id,
                    version_id=version.id,
                    node_key=node.id,
                    expression=node.condition,
                )
            )
        else:
            db.add(
                AutomationAction(
                    tenant_id=tenant_id,
                    version_id=version.id,
                    node_key=node.id,
                    kind=node.type,
                    arguments=node.model_dump(mode="json"),
                )
            )
    for name, value in definition.variables.items():
        db.add(
            AutomationVariable(
                tenant_id=tenant_id, version_id=version.id, name=name, value={"value": value}
            )
        )
    for name, integration_id in definition.credentials.items():
        db.add(
            AutomationCredentialReference(
                tenant_id=tenant_id, version_id=version.id, name=name, integration_id=integration_id
            )
        )
    schedule = await db.scalar(
        select(AutomationSchedule).where(
            AutomationSchedule.tenant_id == tenant_id, AutomationSchedule.automation_id == row.id
        )
    )
    if definition.schedule:
        config = definition.schedule.model_dump(mode="json")
        if not schedule:
            schedule = AutomationSchedule(tenant_id=tenant_id, automation_id=row.id)
            db.add(schedule)
        schedule.configuration, schedule.timezone, schedule.enabled = (
            config,
            definition.schedule.timezone,
            True,
        )
        schedule.scheduled_at = next_occurrence(config, now())
    elif schedule:
        schedule.enabled = False
    row.status, row.updated_at = "ACTIVE", now()
    audit(db, tenant_id, actor_id, "automation.published", "automation_version", version.id)
    await db.flush()
    return row


async def transition(db, tenant_id, actor_id, automation_id, action):
    await authorize(db, tenant_id, actor_id, "automation:write")
    row = await owned(db, Automation, tenant_id, automation_id, True)
    allowed = {
        "pause": {"ACTIVE"},
        "resume": {"PAUSED", "DISABLED"},
        "disable": {"DRAFT", "ACTIVE", "PAUSED"},
        "archive": {"DRAFT", "ACTIVE", "PAUSED", "DISABLED"},
    }
    if action not in allowed or row.status not in allowed[action]:
        raise HTTPException(409, "Invalid automation transition")
    if action == "resume":
        version = await db.scalar(
            select(AutomationVersion).where(
                AutomationVersion.tenant_id == tenant_id,
                AutomationVersion.automation_id == row.id,
                AutomationVersion.number == row.version,
            )
        )
        if not version:
            raise HTTPException(409, "Publish a version before resuming")
        await authorize(db, tenant_id, row.owner_id, "automation:write")
        await check_active_capacity(db, tenant_id, row.id, version.definition["trigger"])
        await validate_chains(db, tenant_id, row.id, Definition.model_validate(version.definition))
    row.status = {
        "pause": "PAUSED",
        "resume": "ACTIVE",
        "disable": "DISABLED",
        "archive": "ARCHIVED",
    }[action]
    audit(db, tenant_id, actor_id, "automation." + row.status.lower(), "automation", row.id)
    return row


async def clone(db, tenant_id, actor_id, automation_id):
    await authorize(db, tenant_id, actor_id, "automation:write")
    row = await owned(db, Automation, tenant_id, automation_id)
    return await save(
        db,
        tenant_id,
        actor_id,
        AutomationInput(
            name=(row.name + " copy")[:255],
            description=row.description,
            definition=Definition.model_validate(row.draft),
        ),
    )


def simulate(definition, context, model_outputs=None):
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
        if node.type in {"ai", "ai_decision"} and current not in (model_outputs or {}):
            result.update(status="requires_live_model_execution", decision=None)
            rows.append(result)
            # Do not invent an AI decision to choose a branch in a side-effect-free test.
            return {
                "dry_run": True,
                "trigger": definition.trigger,
                "steps": rows,
                "remaining_nodes": [n.id for n in definition.nodes[index + 1 :]],
                "blocked_on": current,
            }
        try:
            result["arguments"] = render(node.arguments, context)
            if node.type in {"ai", "ai_decision"}:
                output = model_outputs[current]
                result["model_result"] = output
                if node.type == "ai_decision":
                    next_node = next_node if output["decision"] else false_node
            if node.type == "condition":
                result["matched"] = evaluate(node.condition, context, context.get("before"))
                next_node = next_node if result["matched"] else false_node
            result["requires_approval"] = (
                node.type == "approval"
                or node.action in EXTERNAL
                or "steps." in str(node.arguments)
            )
        except HTTPException:
            result["error"] = "missing_test_variable"
            rows.append(result)
            return {
                "dry_run": True,
                "trigger": definition.trigger,
                "steps": rows,
                "blocked_on": current,
            }
        rows.append(result)
        context["steps"][current] = (model_outputs or {}).get(current, result)
        current = next_node
    return {"dry_run": True, "trigger": definition.trigger, "steps": rows, "remaining_nodes": []}


async def simulate_with_model(db, tenant_id, actor_id, definition, context, gateway=None):
    """Explicit, metered model simulation. No CRM action or provider send is called."""
    import json
    from app.models import AIUsageLog, AutomationStepExecution, AITaskTypeEnum
    from app.schemas.automation import DecisionOutput, IntelligenceOutput
    from app.services.automation.ai import configured_gateway, AUTOMATION_SYSTEM
    from app.services.automation.validation import policy
    from app.services.automation.expressions import render, bounded_context
    from app.services.ai.safety import safe_data
    from app.services.crm.common import meter

    await authorize(db, tenant_id, actor_id, "automation:write")
    await authorize(db, tenant_id, actor_id, "ai:chat")
    spec = validate_structure(definition)
    safe_data(context)
    bounded_context(context)
    limits = await policy(db, tenant_id)
    instance = gateway or configured_gateway()
    outputs, calls = {}, 0
    try:
        while True:
            result = simulate(definition, context, outputs)
            key = result.get("blocked_on")
            if not key or result["steps"][-1].get("status") != "requires_live_model_execution":
                return result
            node = next(node for node in spec.nodes if node.id == key)
            routes = len(instance.routes)
            if calls + routes > limits.max_ai_calls:
                raise HTTPException(403, "Simulation AI call quota reached")
            # Hold admission until the independent usage ledger has committed.
            # Concurrent execution reservations count toward the same quota.
            await serial_key(db, tenant_id, "automation-ai-admission")
            reserved = await db.scalar(
                select(
                    func.coalesce(
                        func.sum(AutomationStepExecution.input["ai_reserved"].as_integer()), 0
                    )
                ).where(
                    AutomationStepExecution.tenant_id == tenant_id,
                    AutomationStepExecution.state == "RUNNING",
                )
            )
            instant = now()
            for boundary, maximum in (
                (instant.replace(hour=0, minute=0, second=0, microsecond=0), limits.daily_ai_calls),
                (
                    instant.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
                    limits.monthly_ai_calls,
                ),
            ):
                used = await db.scalar(
                    select(func.count())
                    .select_from(AIUsageLog)
                    .where(AIUsageLog.tenant_id == tenant_id, AIUsageLog.created_at >= boundary)
                )
                if used + reserved + routes > maximum:
                    raise HTTPException(403, "Tenant AI call quota reached")
            await meter(db, tenant_id, actor_id, "ai_credits", routes)
            facts = {**context, "vars": spec.variables, "steps": outputs}
            bounded_context(facts)
            safe_data(facts)
            arguments = render(node.arguments, facts)
            schema = DecisionOutput if node.type == "ai_decision" else IntelligenceOutput
            generated = await instance.execute(
                db,
                tenant_id,
                actor_id,
                AITaskTypeEnum.CLASSIFICATION,
                "chat",
                messages=[
                    {
                        "role": "system",
                        "content": AUTOMATION_SYSTEM
                        + " Return JSON matching: "
                        + json.dumps(schema.model_json_schema()),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "simulation": True,
                                "instruction": arguments.get(
                                    "instruction", "Analyze supplied test facts"
                                ),
                                "kind": arguments.get("kind"),
                                "UNTRUSTED_DATA": facts,
                            },
                            default=str,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=1500,
                temperature=0,
            )
            output = schema.model_validate_json(generated.content).model_dump(mode="json")
            safe_data(output)
            outputs[key] = {
                **output,
                "provider": generated.provider,
                "model": generated.model,
                "test_input": True,
            }
            calls += routes
            # Persist quota charges even when a later test branch is invalid.
            await db.commit()
    except (HTTPException, ValueError, RuntimeError):
        await db.commit()  # Attempted model usage still consumes reserved entitlement.
        raise
    finally:
        if gateway is None:
            for provider in instance.providers.values():
                await provider.client.aclose()
