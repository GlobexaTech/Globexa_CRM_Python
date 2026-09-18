"""Failure-boundary and concurrent admission evidence for advanced automation."""

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from test_checkpoint7_engine import automation_db, create, tick, drive_flow  # noqa: F401
from test_checkpoint6_workforce import workforce_db, ModelTransport  # noqa: F401
from app.models import AutomationPolicy, AutomationExecution, ApprovalRequest, DeadLetterEvent
from app.schemas.automation import Limits
from app.services.automation.engine import request_execution, transition_execution


async def test_concurrent_admission_serializes_tenant_quota(automation_db):
    from app.core.tenant_context import tenant_db_context

    db, tenant, actor, _, _, _ = automation_db
    row = await create(
        db,
        tenant,
        actor,
        [
            {
                "id": "notice",
                "type": "action",
                "action": "create_notification",
                "arguments": {"message": "Quota"},
            }
        ],
    )
    db.add(
        AutomationPolicy(
            tenant_id=tenant, updated_by=actor, limits=Limits(daily_executions=1).model_dump()
        )
    )
    await db.commit()

    async def enqueue_one(key):
        try:
            async with tenant_db_context(tenant, actor) as session:
                await request_execution(session, tenant, actor, row.id, {}, key)
                return 202
        except HTTPException as exc:
            return exc.status_code

    assert sorted(
        await asyncio.gather(enqueue_one("concurrent-one"), enqueue_one("concurrent-two"))
    ) == [202, 429]
    assert (
        await db.scalar(
            select(func.count())
            .select_from(AutomationExecution)
            .where(AutomationExecution.tenant_id == tenant)
        )
        == 1
    )


async def test_ai_quota_blocks_before_model_transport(automation_db, monkeypatch):
    db, tenant, actor, _, _, _ = automation_db
    monkeypatch.setenv("CRM_AI_PROVIDER", "ollama")
    monkeypatch.setenv("CRM_AI_MODEL", "fixture")
    monkeypatch.setenv("CRM_AI_BASE_URL", "http://127.0.0.1:11434")
    row = await create(
        db, tenant, actor, [{"id": "decision", "type": "ai_decision", "arguments": {}}]
    )
    db.add(
        AutomationPolicy(
            tenant_id=tenant, updated_by=actor, limits=Limits(max_ai_calls=0).model_dump()
        )
    )
    execution = await request_execution(db, tenant, actor, row.id, {}, "quota-blocked-ai")
    await db.commit()
    model = ModelTransport([])
    gateway = model.gateway()
    try:
        await tick(db, tenant, execution, gateway)
        assert execution.state == "FAILED" and execution.error_code == "authorization_denied"
        assert model.requests == []
    finally:
        for provider in gateway.providers.values():
            await provider.client.aclose()


@pytest.mark.parametrize("uncertain", [False, True])
async def test_webhook_retry_after_and_unknown_outcome_never_replayed(
    automation_db, monkeypatch, uncertain
):
    from app.services.automation import webhook

    db, tenant, actor, approver, _, _ = automation_db
    monkeypatch.setenv("AUTOMATION_WEBHOOK_ALLOWED_HOSTS", "public.example")
    calls = []

    async def transport(url, payload, key):
        calls.append(key)
        if len(calls) == 1:
            raise webhook.WebhookFailure(
                "webhook_rate_limited" if not uncertain else "webhook_outcome_unknown",
                retryable=not uncertain,
                uncertain=uncertain,
                retry_after=120,
            )
        return {"status": "sent", "http_status": 200}

    monkeypatch.setattr(webhook, "deliver", transport)
    row = await create(
        db,
        tenant,
        actor,
        [
            {
                "id": "webhook",
                "type": "action",
                "action": "webhook_call",
                "arguments": {
                    "url": "https://public.example/crm",
                    "payload": {"kind": "approved-notification"},
                },
                "max_retries": 1,
            }
        ],
    )
    execution = await request_execution(db, tenant, actor, row.id, {}, "webhook-retry-test")
    await db.commit()
    await drive_flow(db, tenant, approver, execution)
    assert execution.state == ("FAILED" if uncertain else "COMPLETED")
    assert len(calls) == (1 if uncertain else 2)
    if uncertain:
        assert execution.error_code == "external_outcome_unknown"
        with pytest.raises(HTTPException):
            await transition_execution(db, tenant, actor, execution.id, "retry")
        assert (
            await db.scalar(
                select(func.count())
                .select_from(DeadLetterEvent)
                .where(DeadLetterEvent.tenant_id == tenant)
            )
            == 1
        )
    else:
        assert calls[0] == calls[1]


async def test_cancelled_approval_cannot_authorize_action(automation_db):
    from app.services.ai.approval import decide
    from app.schemas.workforce import ApprovalDecision

    db, tenant, actor, approver, _, _ = automation_db
    row = await create(
        db,
        tenant,
        actor,
        [{"id": "approval", "type": "approval", "arguments": {"reason": "Review"}}],
    )
    execution = await request_execution(db, tenant, actor, row.id, {}, "cancelled-approval")
    await db.commit()
    await tick(db, tenant, execution)
    approval = await db.scalar(
        select(ApprovalRequest).where(ApprovalRequest.automation_execution_id == execution.id)
    )
    await transition_execution(db, tenant, actor, execution.id, "cancel")
    await db.commit()
    with pytest.raises(HTTPException) as denied:
        await decide(
            db,
            tenant,
            approver,
            approval.id,
            ApprovalDecision(decision="approved", action_hash=approval.action_hash),
        )
    assert denied.value.status_code == 409


async def test_execution_chain_cannot_return_to_visited_automation(automation_db):
    db, tenant, actor, _, _, _ = automation_db
    row = await create(
        db,
        tenant,
        actor,
        [
            {
                "id": "notice",
                "type": "action",
                "action": "create_notification",
                "arguments": {"message": "Loop guard"},
            }
        ],
    )
    parent = await request_execution(db, tenant, actor, row.id, {}, "chain-parent-test")
    await db.commit()
    with pytest.raises(HTTPException) as denied:
        await request_execution(db, tenant, actor, row.id, {}, "chain-cycle-test", parent=parent)
    assert denied.value.status_code == 409


async def test_stop_current_execution_never_runs_successor(automation_db):
    db, tenant, actor, _, _, _ = automation_db
    row = await create(
        db,
        tenant,
        actor,
        [
            {
                "id": "stop",
                "type": "action",
                "action": "stop_automation",
                "arguments": {"execution_id": "{{automation.execution_id}}"},
            },
            {
                "id": "notice",
                "type": "action",
                "action": "create_notification",
                "arguments": {"message": "Must not execute"},
            },
        ],
    )
    execution = await request_execution(db, tenant, actor, row.id, {}, "self-cancellation-test")
    await db.commit()
    await tick(db, tenant, execution)
    assert execution.state == "CANCELLED" and execution.step_count == 1
    await tick(db, tenant, execution)
    assert execution.state == "CANCELLED" and execution.step_count == 1


async def test_unknown_message_delivery_cannot_continue_or_fallback(automation_db, monkeypatch):
    from test_checkpoint6_workforce import configure_provider
    from app.services.crm.providers import adapters, ProviderFailure
    from app.services.automation.service import save, publish
    from app.schemas.automation import AutomationInput
    from app.models import AutomationNotification

    db, tenant, actor, approver, _, ids = automation_db
    integration, _ = await configure_provider(
        db, tenant, actor, ids["conversation"], "gmail", monkeypatch
    )
    calls = []

    async def uncertain_send(*args):
        calls.append(True)
        raise ProviderFailure("provider_timeout", uncertain=True)

    monkeypatch.setattr(adapters["gmail"], "send", uncertain_send)
    row = await save(
        db,
        tenant,
        actor,
        AutomationInput(
            name="Unknown delivery",
            definition={
                "trigger": "manual",
                "credentials": {"mail": str(integration.id)},
                "nodes": [
                    {
                        "id": "send",
                        "type": "action",
                        "action": "send_email",
                        "on_error": "continue",
                        "arguments": {
                            "conversation_id": str(ids["conversation"]),
                            "recipient": "customer@example.com",
                            "body": "Approved bounded message",
                        },
                    },
                    {
                        "id": "notice",
                        "type": "action",
                        "action": "create_notification",
                        "arguments": {"message": "Must not continue after uncertain send"},
                    },
                ],
            },
        ),
    )
    await publish(db, tenant, actor, row.id)
    execution = await request_execution(db, tenant, actor, row.id, {}, "unknown-delivery-test")
    await db.commit()
    await drive_flow(db, tenant, approver, execution)
    assert execution.state == "FAILED" and execution.error_code == "external_outcome_unknown"
    assert len(calls) == 1
    assert (
        await db.scalar(
            select(func.count())
            .select_from(AutomationNotification)
            .where(AutomationNotification.execution_id == execution.id)
        )
        == 0
    )
    await tick(db, tenant, execution)
    assert execution.state == "FAILED" and len(calls) == 1


async def test_provider_send_rechecks_business_hours_after_queue(automation_db, monkeypatch):
    from app.services.automation import engine

    # Queue admission is open; the actual provider boundary is tested after it closes.
    monkeypatch.setattr(engine, "business_open", lambda *args: True)
    from test_checkpoint6_workforce import configure_provider
    from app.services.automation.service import save, publish
    from app.schemas.automation import AutomationInput
    from app.schemas.workforce import ApprovalDecision
    from app.services.ai import approval as approvals
    from app.services.crm.jobs import execute_job
    from app.models import OperationJob, AutomationStepExecution

    db, tenant, actor, approver, _, ids = automation_db
    integration, calls = await configure_provider(
        db, tenant, actor, ids["conversation"], "gmail", monkeypatch
    )
    row = await save(
        db,
        tenant,
        actor,
        AutomationInput(
            name="Business hours fence",
            definition={
                "trigger": "manual",
                "credentials": {"mail": str(integration.id)},
                "business_hours": {
                    "timezone": "UTC",
                    "weekdays": list(range(7)),
                    "start": "00:00",
                    "end": "23:59",
                },
                "nodes": [
                    {
                        "id": "send",
                        "type": "action",
                        "action": "send_email",
                        "arguments": {
                            "conversation_id": str(ids["conversation"]),
                            "recipient": "customer@example.com",
                            "body": "Business hours test",
                        },
                    }
                ],
            },
        ),
    )
    await publish(db, tenant, actor, row.id)
    execution = await request_execution(db, tenant, actor, row.id, {}, "business-hours-fence")
    await db.commit()
    await tick(db, tenant, execution)
    approval = await db.scalar(
        select(ApprovalRequest).where(ApprovalRequest.automation_execution_id == execution.id)
    )
    await approvals.decide(
        db,
        tenant,
        approver,
        approval.id,
        ApprovalDecision(decision="approved", action_hash=approval.action_hash),
    )
    await db.commit()
    grant = await db.scalar(
        select(OperationJob).where(
            OperationJob.kind == "workforce_approval",
            OperationJob.payload["approval_id"].astext == str(approval.id),
        )
    )
    await execute_job(db, tenant, grant.id)
    await tick(db, tenant, execution)
    step = await db.scalar(
        select(AutomationStepExecution).where(AutomationStepExecution.execution_id == execution.id)
    )
    child = await db.get(OperationJob, step.child_job_id)
    from app.services.crm.common import now as actual_now

    closed = actual_now().replace(hour=23, minute=59, second=30, microsecond=0)
    monkeypatch.setattr(approvals, "now", lambda: closed)
    await execute_job(db, tenant, child.id)
    await db.refresh(child)
    assert child.status == "retry" and child.available_at > closed and calls == []


async def test_publication_rejects_cross_workflow_cycle(automation_db):
    from app.services.automation.service import save, publish
    from app.schemas.automation import AutomationInput

    db, tenant, actor, _, _, _ = automation_db
    first = await create(
        db,
        tenant,
        actor,
        [
            {
                "id": "notice",
                "type": "action",
                "action": "create_notification",
                "arguments": {"message": "A"},
            }
        ],
    )
    second = await create(
        db,
        tenant,
        actor,
        [
            {
                "id": "start",
                "type": "action",
                "action": "start_automation",
                "arguments": {"automation_id": str(first.id)},
            }
        ],
    )
    await save(
        db,
        tenant,
        actor,
        AutomationInput(
            name="Cyclic edit",
            definition={
                "trigger": "manual",
                "nodes": [
                    {
                        "id": "start",
                        "type": "action",
                        "action": "start_automation",
                        "arguments": {"automation_id": str(second.id)},
                    }
                ],
            },
        ),
        first.id,
    )
    with pytest.raises(HTTPException, match="cycle"):
        await publish(db, tenant, actor, first.id)


@pytest.mark.parametrize(
    "url",
    [
        "http://public.example",
        "https://public.example@127.0.0.1",
        "https://127.0.0.1",
        "https://public.example:8443",
        "https://public.example?token=value",
        "https://public.example/#fragment",
    ],
)
def test_webhook_destination_rejects_unapproved_boundaries(monkeypatch, url):
    from app.services.automation.webhook import validate_destination

    monkeypatch.setenv("AUTOMATION_WEBHOOK_ALLOWED_HOSTS", "public.example")
    with pytest.raises(HTTPException):
        validate_destination(url)


async def test_internal_retry_preserves_failed_attempt_audit(automation_db, monkeypatch):
    from app.services.automation import engine
    from app.models import AutomationStepExecution

    db, tenant, actor, approver, _, _ = automation_db
    row = await create(
        db,
        tenant,
        actor,
        [
            {
                "id": "notice",
                "type": "action",
                "action": "create_notification",
                "arguments": {"message": "Retried notification"},
                "max_retries": 1,
            }
        ],
    )
    original = engine.execute_action
    attempts = []

    async def transient_failure(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            raise HTTPException(429, "rate limited before mutation")
        return await original(*args, **kwargs)

    monkeypatch.setattr(engine, "execute_action", transient_failure)
    execution = await request_execution(db, tenant, actor, row.id, {}, "attempt-audit-test")
    await db.commit()
    await drive_flow(db, tenant, approver, execution)
    step = await db.scalar(
        select(AutomationStepExecution).where(AutomationStepExecution.execution_id == execution.id)
    )
    assert execution.state == "COMPLETED"
    assert len(attempts) == step.attempts == 2 and step.retry_count == 1
