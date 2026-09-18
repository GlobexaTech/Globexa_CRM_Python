"""Persistent exact-action approvals. A model can propose, never decide."""

import hashlib
import hmac
import json
from datetime import timedelta
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select
from app.models import ApprovalRequest, OperationJob, RoleEnum
from app.services.crm.common import authorize, owned, audit, serial_key, enqueue, now
from app.services.ai.safety import safe_data


class AutomationSendDeferred(Exception):
    def __init__(self, resume_at):
        self.resume_at = resume_at
        super().__init__("Outside published automation business hours")


def fingerprint(action):
    return hashlib.sha256(
        json.dumps(action, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


async def request_approval(
    db, tenant_id, actor_id, agent_name, name, arguments, key, *, execution_id=None, automation_context=None
):
    from app.services.ai.workforce_tools import (
        validate_arguments,
        validate_ownership,
        action_binding,
    )

    await authorize(db, tenant_id, actor_id, "ai:chat")
    safe_data(arguments)
    if name.startswith("automation:"):
        from app.services.automation.actions import permitted, binding as automation_binding
        if not automation_context:
            raise HTTPException(422, "Automation approval requires execution context")
        arguments = await permitted(db, tenant_id, actor_id, name.removeprefix("automation:"), arguments)
        binding = await automation_binding(db, tenant_id, name.removeprefix("automation:"), arguments)
    elif name == "remember":
        from app.schemas.workforce import MemoryInput

        arguments = MemoryInput.model_validate(arguments).model_dump(mode="json")
        binding = {}
    else:
        arguments = validate_arguments(name, arguments)
        await validate_ownership(db, tenant_id, actor_id, name, arguments)
        binding = await action_binding(db, tenant_id, name, arguments)
    action = {"name": name, "arguments": arguments, "binding": binding}
    if automation_context:
        action["automation"] = {key: str(value) for key, value in automation_context.items()}
    digest = fingerprint(action)
    await serial_key(db, tenant_id, "approval:" + key)
    existing = await db.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.tenant_id == tenant_id, ApprovalRequest.idempotency_key == key
        )
    )
    if existing:
        if existing.requesting_user_id != actor_id or existing.action_hash != digest:
            raise HTTPException(409, "Approval idempotency key has different input")
        return existing
    row = ApprovalRequest(
        tenant_id=tenant_id,
        requesting_user_id=actor_id,
        execution_id=execution_id,
        agent_name=agent_name,
        action_type=name,
        target=str(
            next(
                (
                    arguments[k]
                    for k in (
                        "conversation_id",
                        "entity_id",
                        "lead_id",
                        "task_id",
                        "contact_id",
                        "deal_id",
                        "key",
                    )
                    if arguments.get(k)
                ),
                "new",
            )
        ),
        proposed_action=action,
        action_hash=digest,
        idempotency_key=key,
        expires_at=now() + timedelta(hours=24),
        **(automation_context or {}),
    )
    db.add(row)
    await db.flush()
    audit(db, tenant_id, actor_id, "approval.requested", "approval_request", row.id)
    return row


async def decide(db, tenant_id, actor_id, approval_id, data):
    member = await authorize(db, tenant_id, actor_id, "ai:approve")
    row = await owned(db, ApprovalRequest, tenant_id, approval_id, True)
    if actor_id == row.requesting_user_id or member.role == RoleEnum.AI_AGENT:
        raise HTTPException(403, "Approval requires a different authorized human")
    if row.status != "pending":
        raise HTTPException(409, "Approval was already decided")
    if row.expires_at <= now():
        row.status = "expired"
        await db.commit()
        raise HTTPException(409, "Approval has expired")
    if not hmac.compare_digest(data.action_hash, row.action_hash) or not hmac.compare_digest(
        fingerprint(row.proposed_action), row.action_hash
    ):
        raise HTTPException(409, "Action changed; a new approval is required")
    if row.automation_execution_id:
        from app.services.automation.approvals import validate_context
        await validate_context(db, row)
    if data.decision == "approved" and row.action_type.startswith("automation:"):
        from app.services.automation.approvals import validate_action
        await validate_action(db, row, actor_id)
    elif data.decision == "approved" and row.action_type != "remember":
        from app.services.ai.workforce_tools import validate_ownership, action_binding

        action = row.proposed_action
        await validate_ownership(
            db, tenant_id, row.requesting_user_id, row.action_type, action["arguments"]
        )
        await validate_ownership(db, tenant_id, actor_id, row.action_type, action["arguments"])
        if (
            await action_binding(db, tenant_id, row.action_type, action["arguments"])
            != action["binding"]
        ):
            raise HTTPException(409, "Target or provider changed; a new approval is required")
    row.status, row.decided_at, row.decided_by = data.decision, now(), actor_id
    row.rejection_reason = data.reason if data.decision == "rejected" else None
    if row.status == "approved":
        await enqueue(
            db,
            tenant_id,
            row.requesting_user_id,
            "workforce_approval",
            "approval:" + str(row.id),
            {"approval_id": str(row.id)},
        )
    audit(db, tenant_id, actor_id, "approval." + row.status, "approval_request", row.id)
    await db.flush()
    return row


async def run_approval(db, job):
    row = await owned(db, ApprovalRequest, job.tenant_id, UUID(job.payload["approval_id"]), True)
    if row.status in {"executed", "failed", "rejected", "expired"}:
        return {"approval_id": str(row.id), "status": row.status, "result": row.execution_result}
    if row.status != "approved" or row.requesting_user_id != job.actor_id:
        raise HTTPException(409, "Approval is not executable")
    try:
        async with db.begin_nested():
            if row.expires_at <= now() and not row.execution_result:
                row.status = "expired"
                return {"approval_id": str(row.id), "status": "expired"}
            if not row.decided_by or row.decided_by == row.requesting_user_id:
                raise HTTPException(403, "Independent approval is required")
            member = await authorize(db, job.tenant_id, row.decided_by, "ai:approve")
            await authorize(db, job.tenant_id, job.actor_id, "ai:chat")
            if member.role == RoleEnum.AI_AGENT or not hmac.compare_digest(
                fingerprint(row.proposed_action), row.action_hash
            ):
                raise HTTPException(409, "Approval integrity check failed")
            if row.action_type.startswith("automation:"):
                from app.services.automation.approvals import validate_context, validate_action
                await validate_context(db, row)
                await validate_action(db, row, row.decided_by)
                # The automation step owns execution and crash recovery. This job
                # only grants the exact approval; it cannot perform the action twice.
                row.execution_result = {"authorization_granted": True}
            elif row.execution_result and row.execution_result.get("job_id"):
                child = await owned(
                    db, OperationJob, job.tenant_id, UUID(row.execution_result["job_id"])
                )
                if child.status in {"pending", "running", "retry"}:
                    if row.decided_at < now() - timedelta(minutes=10):
                        row.status = "failed"
                        row.execution_result = {
                            **row.execution_result,
                            "status": "unknown",
                            "error": "delivery_monitor_timeout",
                        }
                        return {"approval_id": str(row.id), "status": row.status}
                    return {"pending": True, "approval_id": str(row.id), "job_id": str(child.id)}
                row.status = "executed" if child.status == "completed" else "failed"
                row.execution_result = {
                    **row.execution_result,
                    "status": child.status,
                    "delivery": child.result,
                    "error": child.error_code,
                }
            elif row.action_type == "remember":
                from app.services.ai.memory import store_approved

                row.execution_result = await store_approved(
                    db,
                    job.tenant_id,
                    job.actor_id,
                    row.decided_by,
                    row.proposed_action["arguments"],
                )
                row.status = "executed"
            else:
                from app.services.ai.workforce_tools import (
                    execute_tool,
                    action_binding,
                    validate_ownership,
                )

                action = row.proposed_action
                await validate_ownership(
                    db, job.tenant_id, row.decided_by, row.action_type, action["arguments"]
                )
                if (
                    await action_binding(db, job.tenant_id, row.action_type, action["arguments"])
                    != action["binding"]
                ):
                    raise HTTPException(409, "Approved target or provider changed")
                row.execution_result = await execute_tool(
                    db,
                    job.tenant_id,
                    job.actor_id,
                    row.action_type,
                    action["arguments"],
                    str(row.id),
                    approved=True,
                )
                if row.execution_result.get("job_id"):
                    child = await owned(
                        db, OperationJob, job.tenant_id, UUID(row.execution_result["job_id"]), True
                    )
                    child.payload = {
                        **child.payload,
                        "approval_id": str(row.id),
                        "approval_action_hash": row.action_hash,
                    }
                    return {
                        "pending": True,
                        "approval_id": str(row.id),
                        "job_id": row.execution_result["job_id"],
                    }
                row.status = "executed"
            audit(
                db,
                job.tenant_id,
                job.actor_id,
                "approval." + row.status,
                "approval_request",
                row.id,
            )
    except (HTTPException, ValueError, KeyError, TypeError):
        row = await owned(
            db, ApprovalRequest, job.tenant_id, UUID(job.payload["approval_id"]), True
        )
        row.status, row.execution_result = "failed", {"error": "approval_execution_rejected"}
        audit(db, job.tenant_id, job.actor_id, "approval.failed", "approval_request", row.id, False)
    return {"approval_id": str(row.id), "status": row.status, "result": row.execution_result}


async def validate_approved_send(db, job, integration):
    """Fence the actual external send, not merely the earlier queue operation."""
    from app.models import Message
    from app.services.ai.workforce_tools import action_binding, validate_ownership

    approval_id = job.payload.get("approval_id")
    if not approval_id:
        return  # An explicitly requested human send uses the normal CRM permissions.
    row = await owned(db, ApprovalRequest, job.tenant_id, UUID(approval_id), True)
    await db.refresh(row)
    automation = bool(row.automation_execution_id)
    if automation:
        from app.services.automation.approvals import validate_context, validate_action
        await validate_context(db, row)
        await validate_action(db, row, row.decided_by)
    if (
        row.action_type not in ({"automation:send_email", "automation:send_whatsapp"} if automation else {"send_email"})
        or row.status != "approved"
        or row.expires_at <= now()
        or row.requesting_user_id != job.actor_id
        or not row.decided_by
        or row.decided_by == row.requesting_user_id
        or job.payload.get("approval_action_hash") != row.action_hash
        or not hmac.compare_digest(fingerprint(row.proposed_action), row.action_hash)
    ):
        raise HTTPException(409, "Send approval is no longer valid")
    member = await authorize(db, job.tenant_id, row.decided_by, "ai:approve")
    if member.role == RoleEnum.AI_AGENT:
        raise HTTPException(403, "Human approval required")
    args = row.proposed_action["arguments"]
    await validate_ownership(db, job.tenant_id, row.requesting_user_id, "send_email", args)
    await validate_ownership(db, job.tenant_id, row.decided_by, "send_email", args)
    binding = await action_binding(db, job.tenant_id, "send_email", args)
    if (
        binding != row.proposed_action["binding"]
        or str(integration.id) != binding["integration_id"]
    ):
        raise HTTPException(409, "Approved provider or credential grant changed")
    expected = {
        "conversation_id": args["conversation_id"],
        "integration_id": binding["integration_id"],
        "recipient": args["recipient"],
        "body": args["body"],
        "subject": binding["subject"],
        "thread_id": binding["thread_id"],
    }
    if any(job.payload.get(key) != value for key, value in expected.items()) or job.payload.get(
        "attachments"
    ) not in (None, []):
        raise HTTPException(409, "Queued send differs from approved action")
    message = await db.scalar(
        select(Message)
        .where(Message.tenant_id == job.tenant_id, Message.idempotency_key == "job:" + str(job.id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        not message
        or str(message.conversation_id) != args["conversation_id"]
        or message.body != args["body"]
        or message.recipient != args["recipient"]
        or message.attachments not in (None, [])
    ):
        raise HTTPException(409, "Queued message differs from approved action")
    if automation:
        from app.models import AutomationVersion
        from app.services.automation.scheduling import business_open, next_business_open
        version = await owned(db, AutomationVersion, job.tenant_id, row.automation_version_id)
        hours = version.definition.get("business_hours")
        if not business_open(hours, now()):
            raise AutomationSendDeferred(next_business_open(hours, now()))
