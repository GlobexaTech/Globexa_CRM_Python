"""Automation bindings extend the shared independent human approval lifecycle."""
import hmac
from uuid import UUID
from fastapi import HTTPException
from app.models import Automation, AutomationVersion, AutomationExecution, AutomationStepExecution, RoleEnum
from app.services.crm.common import owned, authorize, now
from app.services.ai.approval import fingerprint


async def validate_context(db, approval):
    execution = await owned(db, AutomationExecution, approval.tenant_id, approval.automation_execution_id)
    step = await owned(db, AutomationStepExecution, approval.tenant_id, approval.automation_step_id)
    version = await owned(db, AutomationVersion, approval.tenant_id, approval.automation_version_id)
    automation = await owned(db, Automation, approval.tenant_id, execution.automation_id)
    await db.refresh(execution); await db.refresh(step); await db.refresh(automation)
    expected = {"automation_execution_id": str(execution.id), "automation_version_id": str(version.id), "automation_step_id": str(step.id)}
    if (execution.version_id != version.id or step.execution_id != execution.id
            or execution.current_node != step.node_key or execution.actor_id != approval.requesting_user_id
            or execution.state not in {"RUNNING", "WAITING"} or step.state not in {"RUNNING", "WAITING"}
            or automation.status != "ACTIVE" or automation.owner_id != execution.actor_id
            or execution.expires_at <= now() or approval.expires_at <= now()
            or approval.proposed_action.get("automation") != expected
            or step.input.get("arguments") != approval.proposed_action.get("arguments")
            or "automation:" + step.input.get("action", "") != approval.action_type
            or not hmac.compare_digest(version.digest, fingerprint(version.definition))):
        raise HTTPException(409, "Automation approval context changed or stopped")
    return execution, step


async def validate_action(db, approval, approver_id):
    from app.services.automation.actions import permitted, binding
    if not approver_id or approver_id == approval.requesting_user_id:
        raise HTTPException(403, "Independent human approval required")
    member = await authorize(db, approval.tenant_id, approver_id, "ai:approve")
    if member.role == RoleEnum.AI_AGENT:
        raise HTTPException(403, "Independent human approval required")
    await authorize(db, approval.tenant_id, approval.requesting_user_id, "automation:write")
    action = approval.proposed_action
    name = approval.action_type.removeprefix("automation:")
    await permitted(db, approval.tenant_id, approval.requesting_user_id, name, action["arguments"])
    await permitted(db, approval.tenant_id, approver_id, name, action["arguments"])
    if not hmac.compare_digest(fingerprint(action), approval.action_hash) or await binding(db, approval.tenant_id, name, action["arguments"]) != action["binding"]:
        raise HTTPException(409, "Approved action or provider binding changed")


async def request(db, execution, step, action, arguments):
    from app.services.ai.approval import request_approval
    row = await request_approval(db, execution.tenant_id, execution.actor_id, "automation",
        "automation:" + action, arguments, "automation-step:" + str(step.id),
        automation_context={"automation_execution_id": execution.id,
                            "automation_version_id": execution.version_id, "automation_step_id": step.id})
    step.approval_id = row.id
    return row
