from datetime import timedelta
import pytest
import pytest_asyncio
from sqlalchemy import select, update, func
from sqlalchemy.exc import DBAPIError
from fastapi import HTTPException
from test_checkpoint6_workforce import workforce_db  # noqa: F401
from app.models import (
    FeatureEntitlement,
    AutomationVersion,
    AutomationExecution,
    AutomationStepExecution,
    ApprovalRequest,
    OperationJob,
    Task,
)
from app.schemas.automation import AutomationInput
from app.services.automation.service import save, publish, transition
from app.services.automation.engine import request_execution
from app.services.crm.jobs import execute_job
from app.services.crm.common import now


@pytest_asyncio.fixture
async def automation_db(workforce_db):
    db, tenant, actor, approver, viewer, ids = workforce_db
    db.add(
        FeatureEntitlement(
            tenant_id=tenant, feature_key="automation", enabled=True, limit_value=100
        )
    )
    await db.commit()
    try:
        yield workforce_db
    finally:
        await db.rollback()
        await db.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.tenant_id == tenant)
            .values(
                automation_execution_id=None, automation_version_id=None, automation_step_id=None
            )
        )
        await db.execute(
            update(AutomationStepExecution)
            .where(AutomationStepExecution.tenant_id == tenant)
            .values(approval_id=None)
        )
        await db.commit()


async def create(db, tenant, actor, nodes, trigger="manual"):
    row = await save(
        db,
        tenant,
        actor,
        AutomationInput(
            name="Actual persisted automation", definition={"trigger": trigger, "nodes": nodes}
        ),
    )
    await publish(db, tenant, actor, row.id)
    await db.commit()
    return row


async def tick(db, tenant, execution, gateway=None):
    job = await db.scalar(
        select(OperationJob).where(
            OperationJob.tenant_id == tenant,
            OperationJob.payload["execution_id"].astext == str(execution.id),
            OperationJob.kind == "advanced_automation",
        )
    )
    job.available_at = now() - timedelta(seconds=1)
    await db.commit()
    await execute_job(db, tenant, job.id, gateway=gateway)
    await db.refresh(execution)
    return execution


async def test_durable_actions_versions_and_idempotency(automation_db):
    db, tenant, actor, _, _, ids = automation_db
    row = await create(
        db,
        tenant,
        actor,
        [
            {
                "id": "task",
                "type": "action",
                "action": "create_task",
                "arguments": {"title": "Follow up {{lead.title}}", "lead_id": "{{lead.id}}"},
            }
        ],
    )
    execution = await request_execution(
        db,
        tenant,
        actor,
        row.id,
        {"entity_type": "lead", "entity_id": str(ids["lead"])},
        "test-real-idempotency",
    )
    await db.commit()
    same = await request_execution(
        db,
        tenant,
        actor,
        row.id,
        {"entity_type": "lead", "entity_id": str(ids["lead"])},
        "test-real-idempotency",
    )
    assert same.id == execution.id
    before = await db.scalar(select(func.count()).select_from(Task).where(Task.tenant_id == tenant))
    await tick(db, tenant, execution)
    assert execution.state == "COMPLETED"
    await tick(db, tenant, execution)
    assert (
        await db.scalar(select(func.count()).select_from(Task).where(Task.tenant_id == tenant))
        == before + 1
    )
    version = await db.scalar(
        select(AutomationVersion).where(AutomationVersion.id == execution.version_id)
    )
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(AutomationVersion)
                .where(AutomationVersion.id == version.id)
                .values(digest="0" * 64)
            )
    assert execution.version_id == version.id


async def test_wait_persists_without_blocking_worker(automation_db):
    db, tenant, actor, _, _, _ = automation_db
    row = await create(
        db,
        tenant,
        actor,
        [
            {"id": "delay", "type": "delay", "arguments": {"minutes": 10}},
            {
                "id": "notice",
                "type": "action",
                "action": "create_notification",
                "arguments": {"message": "Wait completed"},
            },
        ],
    )
    execution = await request_execution(db, tenant, actor, row.id, {}, "wait-resume-test")
    await db.commit()
    await tick(db, tenant, execution)
    assert execution.state == "WAITING" and execution.resume_at > now() + timedelta(minutes=9)
    step = await db.scalar(
        select(AutomationStepExecution).where(AutomationStepExecution.execution_id == execution.id)
    )
    step.resume_at = now() - timedelta(seconds=1)
    await db.commit()
    await tick(db, tenant, execution)
    await tick(db, tenant, execution)
    assert execution.state == "COMPLETED" and execution.step_count == 2


async def test_paused_and_disabled_automation_do_not_run_actions(automation_db):
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
                "arguments": {"message": "Notice"},
            }
        ],
    )
    execution = await request_execution(db, tenant, actor, row.id, {}, "pause-disable-test")
    await transition(db, tenant, actor, row.id, "pause")
    await db.commit()
    await tick(db, tenant, execution)
    assert execution.state == "QUEUED"
    await transition(db, tenant, actor, row.id, "disable")
    await db.commit()
    await tick(db, tenant, execution)
    assert execution.state == "CANCELLED"


async def test_cross_tenant_entity_and_viewer_cannot_start(automation_db):
    db, tenant, actor, _, viewer, ids = automation_db
    row = await create(
        db,
        tenant,
        actor,
        [
            {
                "id": "notice",
                "type": "action",
                "action": "create_notification",
                "arguments": {"message": "Notice"},
            }
        ],
    )
    with pytest.raises(HTTPException) as denied:
        await request_execution(db, tenant, viewer, row.id, {}, "viewer-request-denied")
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as denied:
        await request_execution(
            db,
            tenant,
            actor,
            row.id,
            {"entity_type": "lead", "entity_id": str(ids["foreign"])},
            "foreign-request-denied",
        )
    assert denied.value.status_code == 404


async def test_revoked_owner_fails_durably(automation_db):
    from app.models import Membership

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
                "arguments": {"message": "Notice"},
            }
        ],
    )
    execution = await request_execution(db, tenant, actor, row.id, {}, "revoked-owner-test")
    await db.execute(
        update(Membership)
        .where(Membership.tenant_id == tenant, Membership.user_id == actor)
        .values(role="viewer")
    )
    await db.commit()
    await tick(db, tenant, execution)
    assert execution.state == "FAILED" and execution.error_code == "authorization_denied"


async def test_independent_approval_is_bound_to_exact_execution(automation_db, monkeypatch):
    from app.services.automation import engine

    original_failure = engine.record_failure
    failures = []

    async def capture_failure(db, row, step, node, exc, next_node, fallback):
        failures.append((type(exc).__name__, getattr(exc, "detail", str(exc))))
        return await original_failure(db, row, step, node, exc, next_node, fallback)

    monkeypatch.setattr(engine, "record_failure", capture_failure)
    from app.services.ai.approval import decide, run_approval
    from app.schemas.workforce import ApprovalDecision

    db, tenant, actor, approver, _, ids = automation_db
    row = await create(
        db,
        tenant,
        actor,
        [
            {"id": "approval", "type": "approval", "arguments": {"reason": "Review follow up"}},
            {
                "id": "task",
                "type": "action",
                "action": "create_task",
                "arguments": {"title": "Approved automation task", "lead_id": str(ids["lead"])},
            },
        ],
    )
    execution = await request_execution(db, tenant, actor, row.id, {}, "exact-approval-test")
    await db.commit()
    await tick(db, tenant, execution)
    assert execution.state == "WAITING"
    approval = await db.scalar(
        select(ApprovalRequest).where(ApprovalRequest.automation_execution_id == execution.id)
    )
    assert approval.automation_version_id == execution.version_id
    decision = ApprovalDecision(decision="approved", action_hash=approval.action_hash)
    with pytest.raises(HTTPException) as denied:
        await decide(db, tenant, actor, approval.id, decision)
    assert denied.value.status_code == 403
    await decide(db, tenant, approver, approval.id, decision)
    await db.commit()
    job = await db.scalar(
        select(OperationJob).where(
            OperationJob.kind == "workforce_approval",
            OperationJob.payload["approval_id"].astext == str(approval.id),
        )
    )
    await run_approval(db, job)
    await db.commit()
    await tick(db, tenant, execution)
    await tick(db, tenant, execution)
    assert execution.state == "COMPLETED", failures
    await db.refresh(approval)
    assert approval.status == "executed"
    assert (
        await db.scalar(
            select(func.count()).select_from(Task).where(Task.title == "Approved automation task")
        )
        == 1
    )


async def test_ai_decision_real_ledger_and_branch(automation_db, monkeypatch):
    from test_checkpoint6_workforce import ModelTransport
    from app.models import AIUsageLog

    db, tenant, actor, _, _, ids = automation_db
    monkeypatch.setenv("CRM_AI_PROVIDER", "ollama")
    monkeypatch.setenv("CRM_AI_MODEL", "fixture-contract-model")
    monkeypatch.setenv("CRM_AI_BASE_URL", "http://127.0.0.1:11434")
    row = await create(
        db,
        tenant,
        actor,
        [
            {
                "id": "decision",
                "type": "ai_decision",
                "arguments": {"instruction": "Assess recorded interest"},
            },
            {
                "id": "notice",
                "type": "action",
                "action": "create_notification",
                "arguments": {"message": "Positive decision"},
            },
        ],
    )
    model = ModelTransport(
        [{"decision": False, "reason": "Insufficient recorded evidence", "confidence": 0.7}]
    )
    gateway = model.gateway()
    try:
        execution = await request_execution(
            db,
            tenant,
            actor,
            row.id,
            {"entity_type": "lead", "entity_id": str(ids["lead"])},
            "ai-decision-test",
        )
        await db.commit()
        await tick(db, tenant, execution, gateway)
        assert execution.state == "COMPLETED" and execution.step_count == 1
        assert execution.output["decision"]["decision"] is False
        usage = await db.scalar(
            select(AIUsageLog).where(AIUsageLog.automation_execution_id == execution.id)
        )
        assert usage.total_tokens == 48 and usage.automation_step_id
        assert execution.ai_calls == 1
        assert len(model.requests) == 1
    finally:
        for provider in gateway.providers.values():
            await provider.client.aclose()


async def test_api_lifecycle_pagination_simulation_and_rbac(automation_db):
    import httpx
    from fastapi import FastAPI
    from app.api.v1.automation import router, identity, get_db

    db, tenant, actor, _, viewer, ids = automation_db
    app = FastAPI()
    app.include_router(router)

    async def scoped():
        yield db

    app.dependency_overrides[get_db] = scoped
    app.dependency_overrides[identity] = lambda: (tenant, actor)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        data = {
            "name": "API workflow",
            "definition": {
                "trigger": "manual",
                "nodes": [
                    {
                        "id": "task",
                        "type": "action",
                        "action": "create_task",
                        "arguments": {"title": "API task", "lead_id": str(ids["lead"])},
                    }
                ],
            },
        }
        response = await client.post("/automation/workflows", json=data)
        assert response.status_code == 201, response.text
        workflow = response.json()["id"]
        assert (await client.post(f"/automation/workflows/{workflow}/validate")).status_code == 200
        assert (
            await client.post(f"/automation/workflows/{workflow}/simulate", json={"context": {}})
        ).json()["dry_run"]
        assert (
            await db.scalar(select(func.count()).select_from(Task).where(Task.title == "API task"))
            == 0
        )
        assert (await client.post(f"/automation/workflows/{workflow}/publish")).json()[
            "version"
        ] == 1
        response = await client.post(
            f"/automation/workflows/{workflow}/execute",
            json={},
            headers={"Idempotency-Key": "api-test-key"},
        )
        assert response.status_code == 202, response.text
        execution = response.json()["id"]
        assert (await client.get(f"/automation/executions/{execution}")).json()["state"] == "QUEUED"
        assert (await client.get("/automation/workflows?limit=101")).status_code == 422
        app.dependency_overrides[identity] = lambda: (tenant, viewer)
        assert (await client.post(f"/automation/workflows/{workflow}/pause")).status_code == 403


async def drive_flow(db, tenant, approver, execution, gateway=None):
    """Use actual worker, approval and delivery services; bound the harness too."""
    from app.schemas.workforce import ApprovalDecision
    from app.services.ai.approval import decide

    for _ in range(30):
        await tick(db, tenant, execution, gateway)
        if execution.state in {"COMPLETED", "FAILED", "CANCELLED", "EXPIRED"}:
            return
        steps = (
            await db.scalars(
                select(AutomationStepExecution).where(
                    AutomationStepExecution.execution_id == execution.id
                )
            )
        ).all()
        for step in steps:
            if step.approval_id:
                approval = await db.get(ApprovalRequest, step.approval_id)
                if approval.status == "pending":
                    await decide(
                        db,
                        tenant,
                        approver,
                        approval.id,
                        ApprovalDecision(decision="approved", action_hash=approval.action_hash),
                    )
                    await db.commit()
                    job = await db.scalar(
                        select(OperationJob).where(
                            OperationJob.kind == "workforce_approval",
                            OperationJob.payload["approval_id"].astext == str(approval.id),
                        )
                    )
                    await execute_job(db, tenant, job.id)
            if step.child_job_id:
                await execute_job(db, tenant, step.child_job_id)
    pytest.fail("Workflow failed to reach a terminal state within bounded harness")


async def test_model_assisted_simulation_records_usage_but_never_mutates_crm(automation_db):
    from test_checkpoint6_workforce import ModelTransport
    from app.models import AIUsageLog
    from app.services.automation.service import simulate_with_model

    db, tenant, actor, _, _, ids = automation_db
    definition = {
        "trigger": "manual",
        "nodes": [
            {"id": "decision", "type": "ai_decision", "arguments": {}},
            {
                "id": "task",
                "type": "action",
                "action": "create_task",
                "arguments": {"title": "Never executed simulation", "lead_id": str(ids["lead"])},
            },
        ],
    }
    model = ModelTransport(
        [{"decision": True, "reason": "Test interest recorded", "confidence": 0.8}]
    )
    gateway = model.gateway()
    try:
        result = await simulate_with_model(
            db, tenant, actor, definition, {"lead": {"title": "Test interest"}}, gateway
        )
        assert result["dry_run"] and len(result["steps"]) == 2
        assert result["steps"][0]["model_result"]["decision"] is True
        assert result["steps"][1]["executed"] is False
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Task)
                .where(Task.title == "Never executed simulation")
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count()).select_from(AIUsageLog).where(AIUsageLog.tenant_id == tenant)
            )
            == 1
        )
    finally:
        for provider in gateway.providers.values():
            await provider.client.aclose()


async def test_e2e_lead_score_decision_approvals_draft_send_analytics(automation_db, monkeypatch):
    from test_checkpoint6_workforce import configure_provider, ModelTransport
    from app.models import Message
    from app.services.automation.intelligence import analytics

    db, tenant, actor, approver, _, ids = automation_db
    integration, calls = await configure_provider(
        db, tenant, actor, ids["conversation"], "gmail", monkeypatch
    )
    monkeypatch.setenv("CRM_AI_PROVIDER", "ollama")
    monkeypatch.setenv("CRM_AI_MODEL", "fixture")
    monkeypatch.setenv("CRM_AI_BASE_URL", "http://127.0.0.1:11434")
    nodes = [
        {"id": "score", "type": "ai", "arguments": {"kind": "score"}},
        {
            "id": "qualify",
            "type": "condition",
            "condition": {"field": "steps.score.score", "operator": "gte", "value": 70},
        },
        {
            "id": "decision",
            "type": "ai_decision",
            "arguments": {"instruction": "Determine whether follow up is justified"},
        },
        {
            "id": "review",
            "type": "approval",
            "arguments": {"reason": "Review follow up recommendation"},
        },
        {"id": "compose", "type": "ai", "arguments": {"kind": "draft"}},
        {
            "id": "draft",
            "type": "action",
            "action": "draft_email",
            "arguments": {
                "conversation_id": str(ids["conversation"]),
                "body": "{{steps.compose.draft}}",
            },
        },
        {
            "id": "send",
            "type": "action",
            "action": "send_email",
            "arguments": {
                "conversation_id": str(ids["conversation"]),
                "recipient": "customer@example.com",
                "body": "{{steps.compose.draft}}",
            },
        },
    ]
    row = await save(
        db,
        tenant,
        actor,
        AutomationInput(
            name="Lead follow up",
            definition={
                "trigger": "lead.created",
                "nodes": nodes,
                "credentials": {"mail": str(integration.id)},
            },
        ),
    )
    await publish(db, tenant, actor, row.id)
    await db.commit()
    model = ModelTransport(
        [
            {"summary": "Recorded interest", "score": 78, "reasons": ["Product interest"]},
            {"decision": True, "reason": "Recorded request merits follow up", "confidence": 0.8},
            {
                "summary": "Draft for human review",
                "draft": "May we schedule your requested product demonstration?",
            },
        ]
    )
    gateway = model.gateway()
    try:
        execution = await request_execution(
            db,
            tenant,
            actor,
            row.id,
            {"entity_type": "lead", "entity_id": str(ids["lead"])},
            "lead-complete-flow",
        )
        await db.commit()
        await drive_flow(db, tenant, approver, execution, gateway)
        assert execution.state == "COMPLETED", (execution.error_code, execution.current_node)
        messages = (
            await db.scalars(
                select(Message).where(
                    Message.conversation_id == ids["conversation"], Message.status == "sent"
                )
            )
        ).all()
        assert (
            len(calls) == 1
            and len(messages) == 1
            and messages[0].provider_message_id == "gmail.outbound"
        )
        report = await analytics(db, tenant, actor, row.id)
        assert (
            report["executions"] == 1
            and report["ai_calls"] == 3
            and report["provider_actions"] == 1
        )
        assert report["approvals"]["executed"] == 3 and report["estimated_cost_usd"] is None
    finally:
        for provider in gateway.providers.values():
            await provider.client.aclose()


async def test_e2e_deal_event_health_next_action_creates_task(automation_db):
    from app.models import Deal, Stage, DomainEvent
    from app.services.automation.engine import AutomationSubscriber

    db, tenant, actor, approver, _, ids = automation_db
    row = await create(
        db,
        tenant,
        actor,
        [
            {"id": "health", "type": "intelligence", "arguments": {"kind": "deal"}},
            {
                "id": "next_action",
                "type": "intelligence",
                "arguments": {"kind": "next_best_action"},
            },
            {
                "id": "task",
                "type": "action",
                "action": "create_task",
                "arguments": {"title": "{{steps.next_action.action}}", "deal_id": "{{deal.id}}"},
            },
        ],
        "deal.stage_changed",
    )
    stage = Stage(tenant_id=tenant, pipeline_id=ids["pipeline"], name="Qualified", order=1)
    db.add(stage)
    await db.flush()
    deal = await db.get(Deal, ids["deal"])
    deal.stage_id = stage.id
    await db.commit()
    event = await db.scalar(
        select(DomainEvent)
        .where(
            DomainEvent.tenant_id == tenant,
            DomainEvent.event_type == "deal.stage_changed",
            DomainEvent.aggregate_id == str(deal.id),
        )
        .order_by(DomainEvent.created_at.desc())
    )
    assert event
    subscriber = AutomationSubscriber()
    await subscriber.handle(db, event)
    await subscriber.handle(db, event)
    await db.commit()
    execution = await db.scalar(
        select(AutomationExecution).where(AutomationExecution.automation_id == row.id)
    )
    await drive_flow(db, tenant, approver, execution)
    assert execution.state == "COMPLETED", execution.error_code
    assert (
        await db.scalar(select(func.count()).select_from(Task).where(Task.deal_id == deal.id)) == 1
    )
    assert (
        await db.scalar(
            select(func.count())
            .select_from(AutomationExecution)
            .where(AutomationExecution.automation_id == row.id)
        )
        == 1
    )


async def test_e2e_inbound_classification_support_draft_approval_send(automation_db, monkeypatch):
    from test_checkpoint6_workforce import configure_provider, ModelTransport
    from app.services.crm.conversations import ingest_message
    from app.services.automation.engine import AutomationSubscriber
    from app.models import Message, DomainEvent

    db, tenant, actor, approver, _, ids = automation_db
    integration, calls = await configure_provider(
        db, tenant, actor, ids["conversation"], "gmail", monkeypatch
    )
    monkeypatch.setenv("CRM_AI_PROVIDER", "ollama")
    monkeypatch.setenv("CRM_AI_MODEL", "fixture")
    monkeypatch.setenv("CRM_AI_BASE_URL", "http://127.0.0.1:11434")
    row = await save(
        db,
        tenant,
        actor,
        AutomationInput(
            name="Support inbound",
            definition={
                "trigger": "message.received",
                "credentials": {"mail": str(integration.id)},
                "nodes": [
                    {"id": "classify", "type": "ai", "arguments": {"kind": "classify"}},
                    {
                        "id": "support",
                        "type": "condition",
                        "condition": {
                            "field": "steps.classify.classification",
                            "operator": "eq",
                            "value": "support",
                        },
                    },
                    {
                        "id": "compose",
                        "type": "ai",
                        "arguments": {
                            "kind": "draft",
                            "instruction": "Prepare a support reply based on the incoming request",
                        },
                    },
                    {
                        "id": "draft",
                        "type": "action",
                        "action": "draft_email",
                        "arguments": {
                            "conversation_id": "{{message.conversation_id}}",
                            "body": "{{steps.compose.draft}}",
                        },
                    },
                    {
                        "id": "send",
                        "type": "action",
                        "action": "send_email",
                        "arguments": {
                            "conversation_id": "{{message.conversation_id}}",
                            "recipient": "customer@example.com",
                            "body": "{{steps.compose.draft}}",
                        },
                    },
                ],
            },
        ),
    )
    await publish(db, tenant, actor, row.id)
    await db.commit()
    await ingest_message(
        db,
        tenant,
        integration,
        {
            "provider_message_id": "support-inbound",
            "thread_id": "support-thread",
            "sender": "customer@example.com",
            "body": "Please help with setup.",
            "subject": "Setup help",
            "occurred_at": now().isoformat(),
        },
    )
    await db.commit()
    event = await db.scalar(
        select(DomainEvent)
        .where(DomainEvent.tenant_id == tenant, DomainEvent.event_type == "message.received")
        .order_by(DomainEvent.created_at.desc())
    )
    assert event
    await AutomationSubscriber().handle(db, event)
    await db.commit()
    execution = await db.scalar(
        select(AutomationExecution).where(AutomationExecution.automation_id == row.id)
    )
    model = ModelTransport(
        [
            {"summary": "Setup request", "classification": "support"},
            {"summary": "Support reply for review", "draft": "Which setup step needs help?"},
        ]
    )
    gateway = model.gateway()
    try:
        await drive_flow(db, tenant, approver, execution, gateway)
        assert execution.state == "COMPLETED", (execution.error_code, execution.current_node)
        assert len(calls) == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.tenant_id == tenant, Message.status == "sent")
            )
            == 1
        )
    finally:
        for provider in gateway.providers.values():
            await provider.client.aclose()
