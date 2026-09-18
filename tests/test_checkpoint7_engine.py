from datetime import timedelta
from uuid import uuid4
import pytest
import pytest_asyncio
from sqlalchemy import select, update, text, func
from sqlalchemy.exc import DBAPIError
from fastapi import HTTPException
from test_checkpoint6_workforce import workforce_db  # noqa: F401
from app.models import (FeatureEntitlement, Automation, AutomationVersion, AutomationExecution,
    AutomationStepExecution, ApprovalRequest, OperationJob, Task)
from app.schemas.automation import AutomationInput
from app.services.automation.service import save, publish, transition
from app.services.automation.engine import request_execution
from app.services.crm.jobs import execute_job
from app.services.crm.common import now


@pytest_asyncio.fixture
async def automation_db(workforce_db):
    db, tenant, actor, approver, viewer, ids = workforce_db
    db.add(FeatureEntitlement(tenant_id=tenant, feature_key="automation", enabled=True, limit_value=100))
    await db.commit()
    try: yield workforce_db
    finally:
        await db.rollback()
        await db.execute(update(ApprovalRequest).where(ApprovalRequest.tenant_id == tenant).values(automation_execution_id=None, automation_version_id=None, automation_step_id=None))
        await db.execute(update(AutomationStepExecution).where(AutomationStepExecution.tenant_id == tenant).values(approval_id=None))
        await db.commit()


async def create(db, tenant, actor, nodes, trigger="manual"):
    row = await save(db, tenant, actor, AutomationInput(name="Actual persisted automation", definition={"trigger": trigger, "nodes": nodes}))
    await publish(db, tenant, actor, row.id)
    await db.commit()
    return row


async def tick(db, tenant, execution):
    job = await db.scalar(select(OperationJob).where(OperationJob.tenant_id == tenant, OperationJob.payload["execution_id"].astext == str(execution.id), OperationJob.kind == "advanced_automation"))
    job.available_at = now() - timedelta(seconds=1)
    await db.commit()
    await execute_job(db, tenant, job.id)
    await db.refresh(execution)
    return execution


async def test_durable_actions_versions_and_idempotency(automation_db):
    db, tenant, actor, _, _, ids = automation_db
    row = await create(db, tenant, actor, [{"id": "task", "type": "action", "action": "create_task", "arguments": {"title": "Follow up {{lead.title}}", "lead_id": "{{lead.id}}"}}])
    execution = await request_execution(db, tenant, actor, row.id, {"entity_type": "lead", "entity_id": str(ids["lead"])}, "test-real-idempotency")
    await db.commit()
    same = await request_execution(db, tenant, actor, row.id, {"entity_type": "lead", "entity_id": str(ids["lead"])}, "test-real-idempotency")
    assert same.id == execution.id
    before = await db.scalar(select(func.count()).select_from(Task).where(Task.tenant_id == tenant))
    await tick(db, tenant, execution)
    assert execution.state == "COMPLETED"
    await tick(db, tenant, execution)
    assert await db.scalar(select(func.count()).select_from(Task).where(Task.tenant_id == tenant)) == before + 1
    version = await db.scalar(select(AutomationVersion).where(AutomationVersion.id == execution.version_id))
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(update(AutomationVersion).where(AutomationVersion.id == version.id).values(digest="0" * 64))
    assert execution.version_id == version.id


async def test_wait_persists_without_blocking_worker(automation_db):
    db, tenant, actor, _, _, _ = automation_db
    row = await create(db, tenant, actor, [{"id": "delay", "type": "delay", "arguments": {"minutes": 10}}, {"id": "notice", "type": "action", "action": "create_notification", "arguments": {"message": "Wait completed"}}])
    execution = await request_execution(db, tenant, actor, row.id, {}, "wait-resume-test")
    await db.commit(); await tick(db, tenant, execution)
    assert execution.state == "WAITING" and execution.resume_at > now() + timedelta(minutes=9)
    step = await db.scalar(select(AutomationStepExecution).where(AutomationStepExecution.execution_id == execution.id))
    step.resume_at = now() - timedelta(seconds=1)
    await db.commit(); await tick(db, tenant, execution); await tick(db, tenant, execution)
    assert execution.state == "COMPLETED" and execution.step_count == 2


async def test_paused_and_disabled_automation_do_not_run_actions(automation_db):
    db, tenant, actor, _, _, _ = automation_db
    row = await create(db, tenant, actor, [{"id": "notice", "type": "action", "action": "create_notification", "arguments": {"message": "Notice"}}])
    execution = await request_execution(db, tenant, actor, row.id, {}, "pause-disable-test")
    await transition(db, tenant, actor, row.id, "pause"); await db.commit()
    await tick(db, tenant, execution); assert execution.state == "QUEUED"
    await transition(db, tenant, actor, row.id, "disable"); await db.commit()
    await tick(db, tenant, execution); assert execution.state == "CANCELLED"


async def test_cross_tenant_entity_and_viewer_cannot_start(automation_db):
    db, tenant, actor, _, viewer, ids = automation_db
    row = await create(db, tenant, actor, [{"id": "notice", "type": "action", "action": "create_notification", "arguments": {"message": "Notice"}}])
    with pytest.raises(HTTPException) as denied:
        await request_execution(db, tenant, viewer, row.id, {}, "viewer-request-denied")
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as denied:
        await request_execution(db, tenant, actor, row.id, {"entity_type": "lead", "entity_id": str(ids["foreign"])}, "foreign-request-denied")
    assert denied.value.status_code == 404
