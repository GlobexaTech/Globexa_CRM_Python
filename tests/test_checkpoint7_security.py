"""Failure-boundary and concurrent admission evidence for advanced automation."""
import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from test_checkpoint7_engine import automation_db, create, tick, drive_flow  # noqa: F401
from test_checkpoint6_workforce import workforce_db, ModelTransport  # noqa: F401
from app.models import (AutomationPolicy, AutomationExecution, ApprovalRequest, DeadLetterEvent)
from app.schemas.automation import Limits
from app.services.automation.engine import request_execution, transition_execution


async def test_concurrent_admission_serializes_tenant_quota(automation_db):
    from app.core.tenant_context import tenant_db_context
    db, tenant, actor, _, _, _ = automation_db
    row = await create(db, tenant, actor, [{"id": "notice", "type": "action", "action": "create_notification", "arguments": {"message": "Quota"}}])
    db.add(AutomationPolicy(tenant_id=tenant, updated_by=actor, limits=Limits(daily_executions=1).model_dump()))
    await db.commit()
    async def enqueue_one(key):
        try:
            async with tenant_db_context(tenant, actor) as session:
                await request_execution(session, tenant, actor, row.id, {}, key)
                return 202
        except HTTPException as exc: return exc.status_code
    assert sorted(await asyncio.gather(enqueue_one("concurrent-one"), enqueue_one("concurrent-two"))) == [202, 429]
    assert await db.scalar(select(func.count()).select_from(AutomationExecution).where(AutomationExecution.tenant_id == tenant)) == 1


async def test_ai_quota_blocks_before_model_transport(automation_db, monkeypatch):
    db, tenant, actor, _, _, _ = automation_db
    monkeypatch.setenv("CRM_AI_PROVIDER", "ollama"); monkeypatch.setenv("CRM_AI_MODEL", "fixture")
    monkeypatch.setenv("CRM_AI_BASE_URL", "http://127.0.0.1:11434")
    row = await create(db, tenant, actor, [{"id": "decision", "type": "ai_decision", "arguments": {}}])
    db.add(AutomationPolicy(tenant_id=tenant, updated_by=actor, limits=Limits(max_ai_calls=0).model_dump()))
    execution = await request_execution(db, tenant, actor, row.id, {}, "quota-blocked-ai")
    await db.commit()
    model = ModelTransport([]); gateway = model.gateway()
    try:
        await tick(db, tenant, execution, gateway)
        assert execution.state == "FAILED" and execution.error_code == "authorization_denied"
        assert model.requests == []
    finally:
        for provider in gateway.providers.values(): await provider.client.aclose()


@pytest.mark.parametrize("uncertain", [False, True])
async def test_webhook_retry_after_and_unknown_outcome_never_replayed(automation_db, monkeypatch, uncertain):
    from app.services.automation import webhook
    db, tenant, actor, approver, _, _ = automation_db
    monkeypatch.setenv("AUTOMATION_WEBHOOK_ALLOWED_HOSTS", "public.example")
    calls = []
    async def transport(url, payload, key):
        calls.append(key)
        if len(calls) == 1:
            raise webhook.WebhookFailure("webhook_rate_limited" if not uncertain else "webhook_outcome_unknown", retryable=not uncertain, uncertain=uncertain, retry_after=120)
        return {"status": "sent", "http_status": 200}
    monkeypatch.setattr(webhook, "deliver", transport)
    row = await create(db, tenant, actor, [{"id": "webhook", "type": "action", "action": "webhook_call", "arguments": {"url": "https://public.example/crm", "payload": {"kind": "approved-notification"}}, "max_retries": 1}])
    execution = await request_execution(db, tenant, actor, row.id, {}, "webhook-retry-test")
    await db.commit()
    await drive_flow(db, tenant, approver, execution)
    assert execution.state == ("FAILED" if uncertain else "COMPLETED")
    assert len(calls) == (1 if uncertain else 2)
    if uncertain:
        assert execution.error_code == "external_outcome_unknown"
        with pytest.raises(HTTPException): await transition_execution(db, tenant, actor, execution.id, "retry")
        assert await db.scalar(select(func.count()).select_from(DeadLetterEvent).where(DeadLetterEvent.tenant_id == tenant)) == 1
    else:
        assert calls[0] == calls[1]


async def test_cancelled_approval_cannot_authorize_action(automation_db):
    from app.services.ai.approval import decide
    from app.schemas.workforce import ApprovalDecision
    db, tenant, actor, approver, _, _ = automation_db
    row = await create(db, tenant, actor, [{"id": "approval", "type": "approval", "arguments": {"reason": "Review"}}])
    execution = await request_execution(db, tenant, actor, row.id, {}, "cancelled-approval")
    await db.commit(); await tick(db, tenant, execution)
    approval = await db.scalar(select(ApprovalRequest).where(ApprovalRequest.automation_execution_id == execution.id))
    await transition_execution(db, tenant, actor, execution.id, "cancel"); await db.commit()
    with pytest.raises(HTTPException) as denied:
        await decide(db, tenant, approver, approval.id, ApprovalDecision(decision="approved", action_hash=approval.action_hash))
    assert denied.value.status_code == 409


async def test_execution_chain_cannot_return_to_visited_automation(automation_db):
    db, tenant, actor, _, _, _ = automation_db
    row = await create(db, tenant, actor, [{"id": "notice", "type": "action", "action": "create_notification", "arguments": {"message": "Loop guard"}}])
    parent = await request_execution(db, tenant, actor, row.id, {}, "chain-parent-test")
    await db.commit()
    with pytest.raises(HTTPException) as denied:
        await request_execution(db, tenant, actor, row.id, {}, "chain-cycle-test", parent=parent)
    assert denied.value.status_code == 409


async def test_stop_current_execution_never_runs_successor(automation_db):
    db, tenant, actor, _, _, _ = automation_db
    row = await create(db, tenant, actor, [
        {"id": "stop", "type": "action", "action": "stop_automation", "arguments": {"execution_id": "{{automation.execution_id}}"}},
        {"id": "notice", "type": "action", "action": "create_notification", "arguments": {"message": "Must not execute"}},
    ])
    execution = await request_execution(db, tenant, actor, row.id, {}, "self-cancellation-test")
    await db.commit(); await tick(db, tenant, execution)
    assert execution.state == "CANCELLED" and execution.step_count == 1
    await tick(db, tenant, execution)
    assert execution.state == "CANCELLED" and execution.step_count == 1


@pytest.mark.parametrize("url", ["http://public.example", "https://public.example@127.0.0.1", "https://127.0.0.1", "https://public.example:8443", "https://public.example?token=value", "https://public.example/#fragment"])
def test_webhook_destination_rejects_unapproved_boundaries(monkeypatch, url):
    from app.services.automation.webhook import validate_destination
    monkeypatch.setenv("AUTOMATION_WEBHOOK_ALLOWED_HOSTS", "public.example")
    with pytest.raises(HTTPException): validate_destination(url)
