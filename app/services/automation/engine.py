"""A durable graph interpreter: one bounded step per delivery, no sleeping workers."""

import hmac
import random
from app.core.events import automation_chain
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import (
    Automation,
    AutomationVersion,
    AutomationTrigger,
    AutomationExecution,
    AutomationStepExecution,
    AutomationSchedule,
    OperationJob,
    ApprovalRequest,
    DeadLetterEvent,
)
from app.schemas.automation import Definition, ExecuteInput
from app.services.crm.common import authorize, owned, audit, serial_key, enqueue, now, meter
from app.services.ai.approval import fingerprint
from app.services.automation.validation import policy, successors
from app.services.automation.expressions import evaluate, render, bounded_context
from app.services.automation.context import snapshot, MODELS
from app.services.automation.actions import execute as execute_action, EXTERNAL, permitted
from app.services.automation.scheduling import business_open, next_business_open, next_occurrence

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "EXPIRED"}


async def request_execution(
    db, tenant_id, actor_id, automation_id, entity, key, *, parent=None, event=None, chain=None
):
    await authorize(db, tenant_id, actor_id, "automation:write")
    data = ExecuteInput.model_validate(entity or {}).model_dump(mode="json", exclude_none=True)
    await snapshot(db, tenant_id, actor_id, data)
    await serial_key(db, tenant_id, "advanced-automation-admission")
    existing = await db.scalar(
        select(AutomationExecution).where(
            AutomationExecution.tenant_id == tenant_id, AutomationExecution.idempotency_key == key
        )
    )
    if existing:
        if existing.automation_id != automation_id or existing.input.get("entity") != data:
            raise HTTPException(409, "Execution idempotency key has different input")
        return existing
    automation = await owned(db, Automation, tenant_id, automation_id, True)
    if automation.status != "ACTIVE":
        raise HTTPException(409, "Automation is not active")
    await authorize(db, tenant_id, automation.owner_id, "automation:write")
    version = await db.scalar(
        select(AutomationVersion).where(
            AutomationVersion.tenant_id == tenant_id,
            AutomationVersion.automation_id == automation_id,
            AutomationVersion.number == automation.version,
        )
    )
    if not version or not hmac.compare_digest(fingerprint(version.definition), version.digest):
        raise HTTPException(409, "Published automation version is invalid")
    limits = await policy(db, tenant_id)
    instant = now()
    for boundary, maximum in (
        (instant.replace(hour=0, minute=0, second=0, microsecond=0), limits.daily_executions),
        (
            instant.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            limits.monthly_executions,
        ),
    ):
        count = await db.scalar(
            select(func.count())
            .select_from(AutomationExecution)
            .where(
                AutomationExecution.tenant_id == tenant_id,
                AutomationExecution.created_at >= boundary,
            )
        )
        if count >= maximum:
            raise HTTPException(429, "Automation execution quota reached")
    queued = await db.scalar(
        select(func.count())
        .select_from(AutomationExecution)
        .where(
            AutomationExecution.tenant_id == tenant_id, AutomationExecution.state.not_in(TERMINAL)
        )
    )
    if queued >= limits.queued_executions:
        raise HTTPException(429, "Automation queue quota reached")
    if parent:
        chain = {
            "chain_id": str(parent.chain_id),
            "depth": parent.depth + 1,
            "visited": parent.visited,
            "correlation_id": str(parent.correlation_id),
        }
    chain = chain or {
        "chain_id": str(uuid4()),
        "depth": 0,
        "visited": [],
        "correlation_id": str(uuid4()),
    }
    visited = chain["visited"]
    if chain["depth"] >= limits.max_depth or any(
        value.split(":", 1)[0] == str(automation_id) for value in visited
    ):
        raise HTTPException(409, "Automation execution chain loop/depth limit reached")
    definition = Definition.model_validate(version.definition)
    row = AutomationExecution(
        tenant_id=tenant_id,
        automation_id=automation_id,
        version_id=version.id,
        actor_id=automation.owner_id,
        event_id=event.id if event else None,
        parent_id=parent.id if parent else None,
        chain_id=UUID(chain["chain_id"]),
        correlation_id=UUID(chain["correlation_id"]),
        depth=chain["depth"],
        visited=[*visited, str(automation_id) + ":" + str(version.id)],
        idempotency_key=key,
        current_node=definition.nodes[0].id,
        expires_at=instant + timedelta(seconds=limits.max_runtime_seconds),
        input={
            "entity": data,
            "event": {
                "id": str(event.id),
                "type": event.event_type,
                "aggregate_id": event.aggregate_id,
            }
            if event
            else {},
            "before": event.payload.get("before", {}) if event else {},
        },
    )
    db.add(row)
    await db.flush()
    await meter(db, tenant_id, actor_id, "automation")
    await enqueue(
        db,
        tenant_id,
        row.actor_id,
        "advanced_automation",
        "advanced:" + str(row.id),
        {"execution_id": str(row.id)},
    )
    audit(db, tenant_id, actor_id, "automation.queued", "automation_execution", row.id)
    return row


def finish(db, row, state, error=None):
    row.state, row.completed_at, row.resume_at, row.error_code = state, now(), None, error
    audit(
        db,
        row.tenant_id,
        row.actor_id,
        "automation." + state.lower(),
        "automation_execution",
        row.id,
        state == "COMPLETED",
    )


async def transition_execution(db, tenant_id, actor_id, execution_id, action):
    await authorize(db, tenant_id, actor_id, "automation:write")
    row = await owned(db, AutomationExecution, tenant_id, execution_id, True)
    if action == "cancel" and row.state not in TERMINAL:
        finish(db, row, "CANCELLED")
    elif action == "pause" and row.state in {"QUEUED", "RUNNING", "WAITING"}:
        row.state = "PAUSED"
    elif action == "resume" and row.state == "PAUSED":
        row.state, row.resume_at = "QUEUED", now()
    elif action == "retry" and row.state == "FAILED":
        step = await db.scalar(
            select(AutomationStepExecution).where(
                AutomationStepExecution.tenant_id == tenant_id,
                AutomationStepExecution.execution_id == row.id,
                AutomationStepExecution.node_key == row.current_node,
            )
        )
        version = await owned(db, AutomationVersion, tenant_id, row.version_id)
        node = next(
            n
            for n in Definition.model_validate(version.definition).nodes
            if n.id == row.current_node
        )
        if (
            not step
            or step.error_code
            not in {"rate_limited", "provider_unavailable", "webhook_rate_limited"}
            or step.retry_count >= node.max_retries
        ):
            raise HTTPException(409, "Only a bounded, known-safe failure can be retried")
        step.retry_count += 1
        step.state, row.state, row.completed_at, row.error_code, row.resume_at = (
            "PENDING",
            "QUEUED",
            None,
            None,
            now(),
        )
    else:
        raise HTTPException(409, "Invalid execution transition")
    job = await db.scalar(
        select(OperationJob)
        .where(
            OperationJob.tenant_id == tenant_id,
            OperationJob.idempotency_key == "advanced:" + str(row.id),
        )
        .with_for_update()
    )
    if job:
        job.status, job.available_at, job.completed_at = (
            ("cancelled" if action == "cancel" else "retry"),
            now(),
            None,
        )
    audit(db, tenant_id, actor_id, "automation.execution." + action, "automation_execution", row.id)
    return row


async def execution_context(db, execution, version):
    context = await snapshot(
        db, execution.tenant_id, execution.actor_id, execution.input.get("entity")
    )
    context.update(
        vars=version.definition.get("variables", {}),
        steps=execution.output,
        event=execution.input.get("event", {}),
        before=execution.input.get("before", {}),
        automation={
            "execution_id": str(execution.id),
            "id": str(execution.automation_id),
            "version": version.number,
            "chain_id": str(execution.chain_id),
        },
    )
    bounded_context(context)
    return context


async def provider_key(db, tenant_id, action, arguments):
    if action in {"send_email", "send_whatsapp"}:
        from app.models import Conversation

        conversation = await owned(db, Conversation, tenant_id, UUID(arguments["conversation_id"]))
        return str(conversation.integration_id)
    if action == "webhook_call":
        from urllib.parse import urlsplit

        return urlsplit(arguments["url"]).hostname
    return ""


async def action_rate(db, execution, node, arguments, limits):
    await serial_key(db, execution.tenant_id, "automation-rate")
    query = (
        select(func.count())
        .select_from(AutomationStepExecution)
        .where(
            AutomationStepExecution.tenant_id == execution.tenant_id,
            AutomationStepExecution.started_at >= now() - timedelta(minutes=1),
        )
    )
    if (await db.scalar(query)) >= limits.tenant_per_minute:
        raise HTTPException(429, "Tenant automation rate limit reached")
    if node.action:
        count = await db.scalar(
            query.where(AutomationStepExecution.input["action"].astext == node.action)
        )
        if count >= limits.action_per_minute:
            raise HTTPException(429, "Automation action rate limit reached")
    if node.action in EXTERNAL:
        provider = await provider_key(db, execution.tenant_id, node.action, arguments)
        count = await db.scalar(
            query.where(AutomationStepExecution.input["provider_key"].astext == provider)
        )
        if count >= limits.provider_per_minute:
            raise HTTPException(429, "Automation provider rate limit reached")


def waiting(row, step, instant):
    row.state, row.resume_at, step.state, step.resume_at = "WAITING", instant, "WAITING", instant


async def run_operation(db, job, gateway=None):
    """Called only from the shared restricted-role worker, with a locked durable job."""
    row = await owned(
        db, AutomationExecution, job.tenant_id, UUID(job.payload["execution_id"]), True
    )
    if row.state in TERMINAL:
        job.status, job.result = "completed", {"execution_id": str(row.id), "status": row.state}
        await db.commit()
        return job
    try:
        await authorize(db, row.tenant_id, row.actor_id, "automation:write")
    except HTTPException:
        finish(db, row, "FAILED", "authorization_denied")
        job.status, job.completed_at = "failed", now()
        job.result = {"execution_id": str(row.id), "status": row.state}
        await db.commit()
        return job
    automation = await owned(db, Automation, row.tenant_id, row.automation_id)
    if row.expires_at <= now():
        finish(db, row, "EXPIRED", "runtime_limit")
    elif automation.status in {"DISABLED", "ARCHIVED"}:
        finish(db, row, "CANCELLED", "automation_disabled")
    elif automation.status == "PAUSED" or row.state == "PAUSED":
        job.status, job.available_at = "retry", now() + timedelta(seconds=60)
        await db.commit()
        return job
    if row.state in TERMINAL:
        job.status = "completed"
        await db.commit()
        return job
    version = await owned(db, AutomationVersion, row.tenant_id, row.version_id)
    if not hmac.compare_digest(version.digest, fingerprint(version.definition)):
        finish(db, row, "FAILED", "version_integrity_failed")
        job.status = "failed"
        await db.commit()
        return job
    definition = Definition.model_validate(version.definition)
    index, node = next((i, n) for i, n in enumerate(definition.nodes) if n.id == row.current_node)
    step = await db.scalar(
        select(AutomationStepExecution)
        .where(
            AutomationStepExecution.tenant_id == row.tenant_id,
            AutomationStepExecution.execution_id == row.id,
            AutomationStepExecution.node_key == node.id,
        )
        .with_for_update()
    )
    if not step:
        step = AutomationStepExecution(
            tenant_id=row.tenant_id, execution_id=row.id, node_key=node.id
        )
        db.add(step)
        await db.flush()
    limits = await policy(db, row.tenant_id)
    if row.step_count >= limits.max_steps:
        finish(db, row, "EXPIRED", "step_limit")
        job.status = "completed"
        await db.commit()
        return job
    if step.state == "RUNNING" and (
        node.type in {"ai", "ai_decision"} or node.action == "webhook_call"
    ):
        step.state, step.error_code = "FAILED", "external_outcome_unknown"
        finish(db, row, "FAILED", step.error_code)
        job.status = "unknown"
        await db.commit()
        return job
    row.state, row.started_at = "RUNNING", row.started_at or now()
    job.status, job.claimed_at, job.attempts = "running", now(), job.attempts + 1
    next_node, false_node, fallback = successors(definition.nodes, index)
    chain_token = automation_chain.set(
        {
            "chain_id": str(row.chain_id),
            "depth": row.depth + 1,
            "visited": row.visited,
            "correlation_id": str(row.correlation_id),
        }
    )
    try:
        context = await execution_context(db, row, version)
        async with db.begin_nested():
            result = None
            if step.child_job_id:
                child = await owned(db, OperationJob, row.tenant_id, step.child_job_id)
                if child.status in {"pending", "retry", "running"}:
                    waiting(row, step, now() + timedelta(seconds=5))
                elif child.status == "completed":
                    result = {**(child.result or {}), "job_id": str(child.id), "status": "sent"}
                else:
                    failure = HTTPException(409, "delivery_" + child.status)
                    failure.uncertain = child.status == "unknown"
                    raise failure
            elif node.type == "condition":
                matched = evaluate(node.condition, context, context.get("before"))
                result = {"matched": matched}
                next_node = next_node if matched else false_node
            elif node.type == "delay":
                args = node.arguments
                if "condition" in args:
                    matched = evaluate(args["condition"], context, context.get("before"))
                    if matched:
                        result = {"matched": True}
                    elif now() >= (step.started_at or now()) + timedelta(
                        seconds=args.get("timeout_seconds", 86400)
                    ):
                        raise HTTPException(408, "wait_condition_expired")
                    else:
                        waiting(row, step, now() + timedelta(seconds=args.get("poll_seconds", 60)))
                else:
                    if step.resume_at:
                        due = step.resume_at
                    elif "until" in args:
                        due = datetime.fromisoformat(args["until"].replace("Z", "+00:00"))
                    else:
                        seconds = sum(
                            args.get(unit, 0) * factor
                            for unit, factor in {
                                "seconds": 1,
                                "minutes": 60,
                                "hours": 3600,
                                "days": 86400,
                            }.items()
                        )
                        due = now() + timedelta(seconds=seconds)
                    if due <= now():
                        result = {"resumed_at": now().isoformat()}
                    else:
                        waiting(row, step, due)
            elif node.type == "intelligence":
                from app.services.automation.intelligence import inspect_entity

                args = render(node.arguments, context)
                entity = row.input.get("entity", {})
                result = await inspect_entity(
                    db,
                    row.tenant_id,
                    row.actor_id,
                    args["kind"],
                    args.get("entity_type", entity.get("entity_type")),
                    UUID(args.get("entity_id", entity.get("entity_id"))),
                )
            elif node.type in {"ai", "ai_decision"}:
                # External execution is handled after committing the durable claim below.
                step.input = {"arguments": render(node.arguments, context), "action": node.type}
                step.state, step.started_at, step.attempts = "RUNNING", now(), step.attempts + 1
            else:
                action = "request_approval" if node.type == "approval" else node.action
                args = (
                    step.input.get("arguments")
                    if step.approval_id
                    else render(node.arguments, context)
                )
                args = await permitted(db, row.tenant_id, row.actor_id, action, args)
                if action in {"send_email", "send_whatsapp"}:
                    from app.models import Conversation

                    conversation = await owned(
                        db, Conversation, row.tenant_id, UUID(args["conversation_id"])
                    )
                    if str(conversation.integration_id) not in {
                        str(v) for v in definition.credentials.values()
                    }:
                        raise HTTPException(
                            403, "Message provider outside published credential scope"
                        )
                hours = (
                    definition.business_hours.model_dump(mode="json")
                    if definition.business_hours
                    else None
                )
                if action in EXTERNAL and not business_open(hours, now()):
                    waiting(row, step, next_business_open(hours, now()))
                else:
                    needs_approval = (
                        action in EXTERNAL
                        or action == "request_approval"
                        or limits.require_internal_approval
                        or "steps." in str(node.arguments)
                    )
                    step.input = {
                        **step.input,
                        "action": action,
                        "arguments": args,
                        "provider_key": await provider_key(db, row.tenant_id, action, args),
                    }
                    approval = None
                    if needs_approval:
                        from app.services.automation.approvals import (
                            request,
                            validate_context,
                            validate_action,
                        )

                        approval = (
                            await owned(db, ApprovalRequest, row.tenant_id, step.approval_id)
                            if step.approval_id
                            else await request(db, row, step, action, args)
                        )
                        if (
                            approval.status in {"rejected", "expired", "failed"}
                            or approval.expires_at <= now()
                        ):
                            raise HTTPException(409, "approval_" + approval.status)
                        if approval.status != "approved" or not (
                            approval.execution_result or {}
                        ).get("authorization_granted"):
                            waiting(row, step, now() + timedelta(seconds=5))
                        else:
                            await db.flush()
                            await validate_context(db, approval)
                            await validate_action(db, approval, approval.decided_by)
                    if row.state != "WAITING":
                        await action_rate(db, row, node, args, limits)
                        step.state, step.started_at, step.attempts = (
                            "RUNNING",
                            now(),
                            step.attempts + 1,
                        )
                        if action != "webhook_call":
                            result = await execute_action(
                                db, row.tenant_id, row.actor_id, action, args, str(step.id), row
                            )
                            if result.get("job_id"):
                                child = await owned(
                                    db, OperationJob, row.tenant_id, UUID(result["job_id"]), True
                                )
                                if approval:
                                    child.payload = {
                                        **child.payload,
                                        "approval_id": str(approval.id),
                                        "approval_action_hash": approval.action_hash,
                                        "_automation_chain": automation_chain.get(),
                                    }
                                step.child_job_id, result = child.id, None
                                waiting(row, step, now() + timedelta(seconds=5))
            step.started_at = step.started_at or now()
            if result is not None:
                await complete_step(db, row, step, result, next_node)
        if step.state == "RUNNING" and (
            node.type in {"ai", "ai_decision"} or node.action == "webhook_call"
        ):
            await db.commit()
            try:
                if node.type in {"ai", "ai_decision"}:
                    from app.services.automation.ai import execute_ai_node

                    result = await execute_ai_node(db, row, step, node, context, gateway=gateway)
                    if node.type == "ai_decision":
                        next_node = next_node if result["decision"] else false_node
                else:
                    approval = await owned(db, ApprovalRequest, row.tenant_id, step.approval_id)
                    from app.services.automation.approvals import validate_context, validate_action

                    await validate_context(db, approval)
                    await validate_action(db, approval, approval.decided_by)
                    result = await execute_action(
                        db,
                        row.tenant_id,
                        row.actor_id,
                        "webhook_call",
                        step.input["arguments"],
                        str(step.id),
                        row,
                    )
                await db.refresh(row, with_for_update=True)
                from app.models import AIUsageLog

                row.ai_calls = await db.scalar(
                    select(func.count())
                    .select_from(AIUsageLog)
                    .where(
                        AIUsageLog.tenant_id == row.tenant_id,
                        AIUsageLog.automation_execution_id == row.id,
                    )
                )
                if row.state in TERMINAL or row.state == "PAUSED":
                    # Preserve actual external outcome even if cancellation arrived in flight.
                    step.result, step.state, step.completed_at = result, "COMPLETED", now()
                else:
                    await complete_step(db, row, step, result, next_node)
            except Exception as exc:
                await db.refresh(row, with_for_update=True)
                from app.models import AIUsageLog

                row.ai_calls = await db.scalar(
                    select(func.count())
                    .select_from(AIUsageLog)
                    .where(
                        AIUsageLog.tenant_id == row.tenant_id,
                        AIUsageLog.automation_execution_id == row.id,
                    )
                )
                await record_failure(db, row, step, node, exc, next_node, fallback)
    except (HTTPException, ValueError, KeyError, TypeError, RuntimeError) as exc:
        await db.refresh(row)
        await db.refresh(step)
        await record_failure(db, row, step, node, exc, next_node, fallback)
    finally:
        automation_chain.reset(chain_token)
    job.status = "completed" if row.state in TERMINAL else "retry"
    job.available_at = row.resume_at or now()
    job.completed_at = now() if row.state in TERMINAL else None
    job.result = {"execution_id": str(row.id), "status": row.state}
    await db.commit()
    return job


async def complete_step(db, row, step, result, next_node):
    from fastapi.encoders import jsonable_encoder

    step.result, step.state, step.completed_at, step.error_code = (
        jsonable_encoder(result),
        "COMPLETED",
        now(),
        None,
    )
    # Pure evaluation nodes have no external claim, but still performed one attempt.
    step.attempts = max(step.attempts, step.retry_count + 1)
    row.output = {**row.output, step.node_key: step.result}
    row.step_count += 1
    if step.approval_id:
        approval = await owned(db, ApprovalRequest, row.tenant_id, step.approval_id)
        approval.status, approval.execution_result = "executed", step.result
    if row.state in TERMINAL:
        # stop_automation may target this execution. Completing that action must
        # not resurrect a cancellation or execute its successor.
        return
    row.current_node, row.resume_at = next_node, None
    if next_node:
        row.state = "QUEUED"
    else:
        finish(db, row, "COMPLETED")
    audit(db, row.tenant_id, row.actor_id, "automation.step.completed", "automation_step", step.id)


async def record_failure(db, row, step, node, exc, next_node, fallback):
    from app.services.automation.webhook import WebhookFailure

    status = exc.status_code if isinstance(exc, HTTPException) else None
    retryable = status == 429 or getattr(exc, "retryable", False)
    uncertain = getattr(exc, "uncertain", False)
    code = (
        "rate_limited"
        if status == 429
        else "authorization_denied"
        if status == 403
        else "resource_unavailable"
        if status == 404
        else "action_rejected"
        if status
        else "invalid_action"
    )
    if isinstance(exc, WebhookFailure):
        code = exc.code
    if getattr(exc, "automation_code", None):
        code = exc.automation_code
    # An internal action savepoint may have rolled back its attempt increment.
    step.attempts = max(step.attempts, step.retry_count + 1)
    step.error_code, step.state = code, "FAILED"
    audit(
        db, row.tenant_id, row.actor_id, "automation.step.failed", "automation_step", step.id, False
    )
    if row.state in TERMINAL:
        return
    if retryable and not uncertain and step.retry_count < node.max_retries:
        step.retry_count += 1
        delay = max(
            getattr(exc, "retry_after", 0),
            min(
                3600,
                node.backoff_seconds * 2 ** (step.retry_count - 1)
                + random.SystemRandom().uniform(0, 3),
            ),
        )
        waiting(row, step, now() + timedelta(seconds=delay))
        audit(db, row.tenant_id, row.actor_id, "automation.step.retry", "automation_step", step.id)
        return
    db.add(
        DeadLetterEvent(
            tenant_id=row.tenant_id,
            provider="automation",
            event_type="automation.step.failed",
            provider_event_id=str(step.id),
            payload={"execution_id": str(row.id), "step_id": str(step.id)},
            error_message=code,
            retry_count=step.retry_count,
        )
    )
    if (
        not uncertain
        and status not in {401, 403, 404}
        and node.on_error in {"continue", "fallback"}
    ):
        step.state, step.completed_at = "SKIPPED", now()
        row.step_count += 1
        row.current_node, row.resume_at = (
            fallback if node.on_error == "fallback" else next_node,
            None,
        )
        row.state = "QUEUED" if row.current_node else "COMPLETED"
        if not row.current_node:
            finish(db, row, "COMPLETED")
    else:
        finish(db, row, "FAILED", "external_outcome_unknown" if uncertain else code)


async def schedule_due(db, tenant_id):
    rows = (
        await db.scalars(
            select(AutomationSchedule)
            .join(Automation, Automation.id == AutomationSchedule.automation_id)
            .where(
                AutomationSchedule.tenant_id == tenant_id,
                Automation.tenant_id == tenant_id,
                Automation.status == "ACTIVE",
                AutomationSchedule.enabled.is_(True),
                AutomationSchedule.scheduled_at <= now(),
            )
            .order_by(AutomationSchedule.scheduled_at, AutomationSchedule.id)
            .limit(25)
            .with_for_update(of=AutomationSchedule, skip_locked=True)
        )
    ).all()
    for schedule in rows:
        automation = await owned(db, Automation, tenant_id, schedule.automation_id)
        if automation.status != "ACTIVE":
            continue
        slot = schedule.scheduled_at
        try:
            async with db.begin_nested():
                await request_execution(
                    db,
                    tenant_id,
                    automation.owner_id,
                    automation.id,
                    {},
                    "schedule:" + str(schedule.id) + ":" + slot.isoformat(),
                )
        except HTTPException as exc:
            audit(
                db,
                tenant_id,
                automation.owner_id,
                "automation.schedule.blocked",
                "automation",
                automation.id,
                False,
            )
            if exc.status_code == 429:
                continue
        schedule.last_run_at = slot
        schedule.scheduled_at = next_occurrence(schedule.configuration, now())
        schedule.enabled = schedule.scheduled_at is not None


class AutomationSubscriber:
    name = "crm.advanced_automation.v1"
    from app.schemas.automation import TRIGGERS

    event_types = set(TRIGGERS) - {"manual", "api", "scheduled"}

    async def handle(self, db, event):
        rows = (
            await db.scalars(
                select(Automation)
                .join(AutomationVersion, AutomationVersion.automation_id == Automation.id)
                .join(AutomationTrigger, AutomationTrigger.version_id == AutomationVersion.id)
                .where(
                    Automation.tenant_id == event.tenant_id,
                    Automation.status == "ACTIVE",
                    AutomationVersion.number == Automation.version,
                    AutomationTrigger.event_type == event.event_type,
                )
                .limit(100)
            )
        ).all()
        kind = event.event_type.split(".")[0].lower()
        entity = {"entity_type": kind, "entity_id": event.aggregate_id} if kind in MODELS else {}
        if event.event_type in {"AI.score_changed", "form.submitted"}:
            entity = {"entity_type": "lead", "entity_id": event.aggregate_id}
        for automation in rows:
            try:
                async with db.begin_nested():
                    await request_execution(
                        db,
                        event.tenant_id,
                        automation.owner_id,
                        automation.id,
                        entity,
                        "event:" + str(event.id) + ":" + str(automation.id),
                        event=event,
                        chain=event.payload.get("_automation_chain"),
                    )
            except HTTPException:
                audit(
                    db,
                    event.tenant_id,
                    automation.owner_id,
                    "automation.trigger.blocked",
                    "automation",
                    automation.id,
                    False,
                )
