"""AI capabilities use the real gateway and independent PostgreSQL usage ledger."""

import json
import os
from uuid import uuid4
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import IntegrityError
import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.core.tenant_context import tenant_db_context
from app.core.security import hash_password
from app.models import (
    Base,
    Tenant,
    User,
    Membership,
    Lead,
    Deal,
    Pipeline,
    Stage,
    Conversation,
    Message,
    Campaign,
    FeatureEntitlement,
    AIInsight,
    AIUsageLog,
    UsageRecord,
    OperationJob,
)
from app.services.crm.ai import request_ai
from app.services.crm.jobs import execute_job
from app.services.ai.gateway import AIGateway, Generation, ModelRoute


@pytest_asyncio.fixture
async def ai_db(monkeypatch):
    settings = get_settings()
    admin = create_async_engine(settings.database.url, poolclass=NullPool)
    tenant, user = uuid4(), uuid4()
    async with async_sessionmaker(admin, expire_on_commit=False)() as db:
        db.add(Tenant(id=tenant, name="AI test", slug=str(tenant)))
        db.add(
            User(
                id=user,
                email=f"ai-{user}@example.com",
                full_name="AI Test",
                hashed_password=hash_password(str(uuid4())),
                is_active=True,
            )
        )
        await db.flush()
        db.add(Membership(tenant_id=tenant, user_id=user, role="admin"))
        db.add(
            FeatureEntitlement(
                tenant_id=tenant, feature_key="ai_credits", enabled=True, limit_value=20
            )
        )
        pipeline = Pipeline(tenant_id=tenant, name="AI Sales")
        db.add(pipeline)
        await db.flush()
        stage = Stage(tenant_id=tenant, pipeline_id=pipeline.id, name="New", order=1)
        conversation = Conversation(tenant_id=tenant, subject="AI reply")
        lead = Lead(tenant_id=tenant, title="Verified lead facts", created_by_id=user)
        campaign = Campaign(
            tenant_id=tenant,
            name="Draft campaign",
            type="broadcast",
            sender_name="Sales",
            sender_email="sales@example.com",
            created_by_id=user,
        )
        db.add_all([stage, conversation, lead, campaign])
        await db.flush()
        deal = Deal(
            tenant_id=tenant,
            title="Proposal facts",
            pipeline_id=pipeline.id,
            stage_id=stage.id,
            created_by_id=user,
        )
        message = Message(
            tenant_id=tenant,
            conversation_id=conversation.id,
            body="Can we schedule a meeting?",
        )
        db.add_all([deal, message])
        await db.commit()
        ids = {
            "lead_score": lead.id,
            "lead_summary": lead.id,
            "next_best_action": deal.id,
            "reply_analysis": message.id,
            "campaign_draft": campaign.id,
            "proposal_draft": deal.id,
        }
    monkeypatch.setattr(settings.database, "username", "globexa_runtime")
    monkeypatch.setattr(
        settings.database,
        "password",
        os.environ.get("RUNTIME_DATABASE_PASSWORD", "checkpoint2-local-isolated-test"),
    )
    try:
        async with tenant_db_context(tenant, user) as db:
            yield db, tenant, user, ids
    finally:
        # Remove only this fixture's committed rows, respecting FK dependency order.
        async with async_sessionmaker(admin)() as db:
            tables = [t for t in Base.metadata.tables.values() if "tenant_id" in t.c]
            for _ in range(len(tables)):
                blocked = []
                for table in tables:
                    try:
                        async with db.begin_nested():
                            await db.execute(
                                delete(table).where(table.c.tenant_id == tenant)
                            )
                    except IntegrityError:
                        blocked.append(table)
                tables = blocked
                if not tables:
                    break
            assert not tables, "Fixture cleanup must remove every tenant-owned row"
            await db.execute(delete(Tenant).where(Tenant.id == tenant))
            await db.execute(delete(User).where(User.id == user))
            await db.commit()
        await admin.dispose()


class ModelProvider:
    def __init__(self, output=None, failure=False):
        self.output, self.failure, self.calls = output, failure, 0

    async def generate(self, model, prompt):
        self.calls += 1
        if self.failure:
            raise RuntimeError("synthetic provider failure")
        return Generation(json.dumps(self.output), 20, 10)


OUTPUTS = {
    "lead_score": {"score": 78, "confidence": 0.8, "reasons": ["Explicit interest"]},
    "lead_summary": {"summary": "Lead is ready for a follow-up."},
    "next_best_action": {
        "action": "Schedule discovery",
        "confidence": 0.7,
        "reasons": ["Open opportunity"],
    },
    "reply_analysis": {
        "classification": "meeting_request",
        "confidence": 0.9,
        "summary": "Asks to meet.",
    },
    "campaign_draft": {"subject": "An update", "body": "Draft for human review."},
    "proposal_draft": {
        "subject": "Proposal draft",
        "body": "Scope based on provided facts.",
    },
}


@pytest.mark.parametrize("capability", OUTPUTS)
async def test_controlled_ai_capability_is_metered_and_idempotent(ai_db, capability):
    db, tenant, user, ids = ai_db
    job = await request_ai(db, tenant, user, capability, ids[capability], "request-1")
    await db.commit()
    provider = ModelProvider(OUTPUTS[capability])
    gateway = AIGateway({"nvidia": provider}, [ModelRoute("nvidia", "test-model")])
    await execute_job(db, tenant, job.id, gateway=gateway)
    await execute_job(db, tenant, job.id, gateway=gateway)
    assert job.status == "completed", job.error_code
    assert provider.calls == 1
    insight = await db.scalar(select(AIInsight).where(AIInsight.job_id == job.id))
    assert insight.output == OUTPUTS[capability]
    assert await db.scalar(select(func.count()).select_from(AIUsageLog)) == 1
    assert (
        await db.scalar(
            select(func.count())
            .select_from(UsageRecord)
            .where(UsageRecord.metric == "ai_credits")
        )
        == 1
    )


async def test_failed_ai_call_keeps_durable_usage_and_no_insight(ai_db):
    db, tenant, user, ids = ai_db
    job = await request_ai(
        db, tenant, user, "lead_score", ids["lead_score"], "request-failure"
    )
    await db.commit()
    provider = ModelProvider(failure=True)
    gateway = AIGateway({"nvidia": provider}, [ModelRoute("nvidia", "test-model")])
    await execute_job(db, tenant, job.id, gateway=gateway)
    assert job.status == "failed"
    assert await db.scalar(select(func.count()).select_from(AIInsight)) == 0
    assert await db.scalar(select(AIUsageLog.success)) is False
    assert await db.scalar(select(func.count()).select_from(UsageRecord)) == 1


async def test_invalid_model_output_is_not_applied(ai_db):
    db, tenant, user, ids = ai_db
    job = await request_ai(
        db, tenant, user, "lead_score", ids["lead_score"], "invalid-output"
    )
    await db.commit()
    provider = ModelProvider({"score": 900, "confidence": 2, "reasons": []})
    await execute_job(
        db,
        tenant,
        job.id,
        gateway=AIGateway({"nvidia": provider}, [ModelRoute("nvidia", "test-model")]),
    )
    assert job.status == "failed"
    assert await db.scalar(select(func.count()).select_from(AIInsight)) == 0


async def test_real_redis_celery_worker_executes_tenant_workflow(ai_db):
    from celery.contrib.testing.worker import start_worker
    from celery.result import allow_join_result
    from app.workers.celery_app import celery_app
    from app.workers.tasks.crm_tasks import execute_operation
    from app.services.crm.automation import (
        save_workflow,
        toggle_workflow,
        trigger_workflows,
    )
    from app.schemas.operations import WorkflowInput
    from app.core.events import publish_event
    from app.models import Task

    db, tenant, user, ids = ai_db
    db.add(
        FeatureEntitlement(
            tenant_id=tenant, feature_key="automation", enabled=True, limit_value=10
        )
    )
    await db.flush()
    workflow = await save_workflow(
        db,
        tenant,
        user,
        WorkflowInput(
            name="Worker test",
            trigger="lead.created",
            actions=[
                {
                    "tool": "create_task",
                    "arguments": {"title": "Real worker task", "lead_id": "$event.id"},
                }
            ],
        ),
    )
    await toggle_workflow(db, tenant, user, workflow.id, True)
    event = publish_event(
        db,
        tenant_id=tenant,
        actor_id=user,
        event_type="lead.created",
        aggregate_id=ids["lead_score"],
    )
    await db.flush()
    await trigger_workflows(db, event)
    job = await db.scalar(select(OperationJob).where(OperationJob.kind == "automation"))
    job_id = job.id
    await db.commit()
    queue = "cp3-test-" + str(uuid4())
    with start_worker(
        celery_app,
        pool="solo",
        concurrency=1,
        perform_ping_check=False,
        queues=[queue],
        shutdown_timeout=20,
    ):
        result = execute_operation.apply_async(
            kwargs={"tenant_id": str(tenant), "job_id": str(job_id)}, queue=queue
        )
        with allow_join_result():
            result.get(timeout=20)
        result.forget()
    await db.refresh(job)
    assert job.status == "completed", job.error_code
    assert await db.scalar(select(Task.title)) == "Real worker task"
