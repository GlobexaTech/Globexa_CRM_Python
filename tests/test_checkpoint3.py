"""Real PostgreSQL CRM contract tests; only external provider transports are substituted."""

from datetime import timedelta
from uuid import UUID, uuid4
import pytest_asyncio
from sqlalchemy import select, func, text
from cryptography.fernet import Fernet
from app.core.config import get_settings
from app.core.events import dispatch_event
from app.models import (
    Company,
    Contact,
    Pipeline,
    Stage,
    FeatureEntitlement,
    Integration,
    OAuthToken,
    Conversation,
    Message,
    DomainEvent,
    OperationJob,
    AnalyticsEvent,
    ExecutionLog,
    Task,
    Campaign,
    CampaignRecipient,
    UsageRecord,
    Membership,
    RoleEnum,
)
from app.services.crm.common import now
from app.services.crm.jobs import execute_job
from app.services.crm.providers import adapters, ProviderFailure, MailAdapter


class MockMail(MailAdapter):
    def __init__(self):
        super().__init__("gmail")
        self.sent = []
        self.inbox = []
        self.failure = None
        self.refreshes = 0

    async def send(self, token, message, idempotency_key):
        if self.failure:
            raise self.failure
        self.sent.append((idempotency_key, message))
        return {"provider_message_id": "external-" + idempotency_key, "status": "sent"}

    async def sync(self, token, cursor=None):
        return {"messages": self.inbox, "cursor": None}

    async def connect(self, code, verifier, redirect_uri):
        return {
            "access_token": "synthetic-provider-access",
            "refresh_token": "synthetic-provider-refresh",
            "expires_in": 3600,
        }

    async def refresh(self, token):
        self.refreshes += 1
        return {"access_token": "rotated-synthetic-access", "expires_in": 3600}

    async def disconnect(self, token):
        return {"remote_revocation": True}


@pytest_asyncio.fixture
async def crm(db_session, test_tenant, test_user, auth_headers, monkeypatch):
    monkeypatch.setattr(
        get_settings().security,
        "credential_encryption_key",
        Fernet.generate_key().decode(),
    )
    mock = MockMail()
    monkeypatch.setitem(adapters, "gmail", mock)
    for suffix in ("CLIENT_ID", "CLIENT_SECRET"):
        monkeypatch.setenv("CRM_GMAIL_" + suffix, "synthetic-oauth-fixture")
    monkeypatch.setenv(
        "CRM_GMAIL_REDIRECT_URI", "https://crm.example.com/oauth/callback"
    )
    monkeypatch.setenv("CRM_PUBLIC_BASE_URL", "https://crm.example.com")
    for feature in (
        "automation",
        "ai_credits",
        "messages",
        "campaigns",
        "integrations",
        "users",
        "storage",
    ):
        db_session.add(
            FeatureEntitlement(
                tenant_id=test_tenant.id,
                feature_key=feature,
                enabled=True,
                limit_value=100,
            )
        )
    company = Company(tenant_id=test_tenant.id, name="Acme Customer")
    pipeline = Pipeline(tenant_id=test_tenant.id, name="Sales")
    integration = Integration(
        tenant_id=test_tenant.id,
        name="Gmail",
        type="email_inbox",
        status="connected",
        created_by_id=test_user.id,
        config={"provider": "gmail"},
    )
    db_session.add_all([company, pipeline, integration])
    await db_session.flush()
    contact = Contact(
        tenant_id=test_tenant.id,
        company_id=company.id,
        first_name="Alice",
        last_name="Customer",
        email="alice@example.com",
    )
    stage = Stage(
        tenant_id=test_tenant.id, pipeline_id=pipeline.id, name="New", order=0
    )
    stage2 = Stage(
        tenant_id=test_tenant.id, pipeline_id=pipeline.id, name="Qualified", order=1
    )
    db_session.add_all(
        [
            contact,
            stage,
            stage2,
            OAuthToken(
                tenant_id=test_tenant.id,
                integration_id=integration.id,
                access_token="synthetic-access",
                refresh_token="synthetic-refresh",
                expires_at=now() + timedelta(hours=1),
            ),
        ]
    )
    await db_session.flush()
    from app.core.tenant_context import bind_context

    await db_session.execute(text("SET LOCAL ROLE globexa_runtime"))
    await bind_context(db_session, test_tenant.id, test_user.id)
    return dict(
        tenant=test_tenant.id,
        user=test_user.id,
        company=company,
        contact=contact,
        pipeline=pipeline,
        stage=stage,
        stage2=stage2,
        integration=integration,
        mock=mock,
        headers=auth_headers,
    )


async def post(client, crm, path, data=None, key="test-operation-0001", method="POST"):
    return await client.request(
        method,
        "/api/v1" + path,
        headers={**crm["headers"], "Idempotency-Key": key},
        json=data,
    )


async def dispatch_all(db, tenant):
    events = (
        await db.scalars(
            select(DomainEvent)
            .where(DomainEvent.tenant_id == tenant)
            .order_by(DomainEvent.created_at)
        )
    ).all()
    for event in events:
        await dispatch_event(db, event.id)
    await db.flush()


async def test_lead_task_activity_customer_contract(client, db_session, crm):
    response = await post(
        client,
        crm,
        "/leads",
        {
            "title": "Acme lead",
            "contact_id": str(crm["contact"].id),
            "company_id": str(crm["company"].id),
        },
    )
    assert response.status_code == 201, response.text
    lead_id = response.json()["id"]
    response = await post(
        client, crm, "/leads/" + lead_id, {"title": "Acme qualified"}, method="PATCH"
    )
    assert response.status_code == 200, response.text
    response = await post(
        client, crm, "/tasks", {"title": "Call customer", "lead_id": lead_id}
    )
    assert response.status_code == 201, response.text
    response = await post(
        client,
        crm,
        "/operations/activities",
        {"subject": "Discovery meeting", "lead_id": lead_id},
    )
    assert response.status_code == 201, response.text
    response = await client.get(
        f"/api/v1/operations/customers/leads/{lead_id}", headers=crm["headers"]
    )
    assert response.status_code == 200, response.text
    assert response.json()["sections"]["tasks"][0]["title"] == "Call customer"
    assert {e["type"] for e in response.json()["timeline"]} >= {
        "lead.created",
        "lead.updated",
        "task.created",
        "activity.created",
    }


async def test_deal_event_analytics_and_automation_contract(client, db_session, crm):
    workflow = await post(
        client,
        crm,
        "/operations/workflows",
        {
            "name": "Follow up qualified",
            "trigger": "deal.stage_changed",
            "conditions": [{"field": "stage_id", "value": str(crm["stage2"].id)}],
            "actions": [
                {
                    "tool": "create_task",
                    "arguments": {"title": "Stage followup", "deal_id": "$event.id"},
                }
            ],
        },
    )
    assert workflow.status_code == 201, workflow.text
    wid = workflow.json()["id"]
    enabled = await post(
        client,
        crm,
        f"/operations/workflows/{wid}/enabled",
        {"enabled": True},
        method="PATCH",
    )
    assert enabled.status_code == 200, enabled.text
    deal = await post(
        client,
        crm,
        "/deals",
        {
            "title": "Acme deal",
            "pipeline_id": str(crm["pipeline"].id),
            "stage_id": str(crm["stage"].id),
            "contact_id": str(crm["contact"].id),
            "company_id": str(crm["company"].id),
            "value": 12000,
        },
    )
    assert deal.status_code == 201, deal.text
    did = deal.json()["id"]
    moved = await post(
        client,
        crm,
        "/deals/" + did,
        {"stage_id": str(crm["stage2"].id)},
        method="PATCH",
    )
    assert moved.status_code == 200, moved.text
    await dispatch_all(db_session, crm["tenant"])
    jobs = (
        await db_session.scalars(
            select(OperationJob).where(OperationJob.kind == "automation")
        )
    ).all()
    assert len(jobs) == 1
    await execute_job(db_session, crm["tenant"], jobs[0].id)
    await execute_job(db_session, crm["tenant"], jobs[0].id)
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Task).where(Task.title == "Stage followup")
        )
        == 1
    )
    assert await db_session.scalar(select(ExecutionLog.status)) == "completed"
    response = await client.get(
        "/api/v1/operations/analytics/pipeline", headers=crm["headers"]
    )
    assert response.status_code == 200, response.text
    assert any(
        s["deals"] == 1 and s["name"] == "Qualified" for s in response.json()["stages"]
    )


async def test_conversation_send_deduplication_and_history(client, db_session, crm):
    response = await post(
        client,
        crm,
        "/operations/conversations",
        {
            "subject": "Customer thread",
            "contact_id": str(crm["contact"].id),
            "integration_id": str(crm["integration"].id),
            "participants": [{"address": "alice@example.com"}],
        },
    )
    assert response.status_code == 201, response.text
    cid = response.json()["id"]
    data = {"recipient": "alice@example.com", "body": "Hello customer"}
    first = await post(client, crm, f"/operations/conversations/{cid}/messages", data)
    assert first.status_code == 202, first.text
    second = await post(client, crm, f"/operations/conversations/{cid}/messages", data)
    assert first.json()["id"] == second.json()["id"]
    job_id = UUID(first.json()["id"])
    await execute_job(db_session, crm["tenant"], job_id)
    await execute_job(db_session, crm["tenant"], job_id)
    assert len(crm["mock"].sent) == 1
    response = await client.get(
        f"/api/v1/operations/conversations/{cid}/messages", headers=crm["headers"]
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["status"] == "sent"
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(UsageRecord)
            .where(UsageRecord.metric == "messages")
        )
        == 1
    )


async def test_sync_inbound_conversation_unread_and_replay(client, db_session, crm):
    crm["mock"].inbox = [
        {
            "provider_message_id": "incoming-1",
            "thread_id": "thread-1",
            "sender": "alice@example.com",
            "recipient": "sales@example.com",
            "subject": "Question about Acme",
            "body": "Can we meet?",
            "occurred_at": now().isoformat(),
        }
    ]
    response = await post(
        client, crm, f"/operations/integrations/{crm['integration'].id}/sync"
    )
    assert response.status_code == 202, response.text
    await execute_job(db_session, crm["tenant"], UUID(response.json()["id"]))
    await dispatch_all(db_session, crm["tenant"])
    await dispatch_all(db_session, crm["tenant"])
    conversation = await db_session.scalar(select(Conversation))
    assert conversation.unread_count == 1
    response = await post(
        client,
        crm,
        f"/operations/integrations/{crm['integration'].id}/sync",
        key="another-sync-key",
    )
    await execute_job(db_session, crm["tenant"], UUID(response.json()["id"]))
    assert await db_session.scalar(select(func.count()).select_from(Message)) == 1
    response = await client.get(
        f"/api/v1/operations/customers/contacts/{crm['contact'].id}",
        headers=crm["headers"],
    )
    assert response.json()["sections"]["conversations"]
    response = await post(
        client, crm, f"/operations/conversations/{conversation.id}/read"
    )
    assert response.json()["unread_count"] == 0


async def prepare_campaign(client, crm, steps=None):
    response = await post(
        client,
        crm,
        "/campaigns",
        {
            "name": "Acme announcement",
            "sender_name": "Sales",
            "sender_email": "sales@example.com",
        },
    )
    assert response.status_code == 201, response.text
    cid = response.json()["id"]
    response = await post(
        client,
        crm,
        f"/operations/campaigns/{cid}/plan",
        {
            "integration_id": str(crm["integration"].id),
            "contact_ids": [str(crm["contact"].id)],
            "subject": "News",
            "body": "Customer update",
            "steps": steps or [],
        },
        method="PUT",
    )
    assert response.status_code == 200, response.text
    return cid


async def test_campaign_schedule_execute_and_statistics(client, db_session, crm):
    cid = await prepare_campaign(client, crm)
    response = await post(
        client,
        crm,
        f"/operations/campaigns/{cid}/schedule",
        {"scheduled_at": (now() + timedelta(minutes=10)).isoformat()},
    )
    assert response.status_code == 200, response.text
    campaign = await db_session.get(Campaign, UUID(cid))
    campaign.scheduled_at = now() - timedelta(seconds=1)
    await db_session.flush()
    from app.workers.tasks.crm_tasks import schedule_due

    await schedule_due(db_session, crm["tenant"])
    job = await db_session.scalar(
        select(OperationJob).where(OperationJob.kind == "campaign_send")
    )
    assert job is not None
    await execute_job(db_session, crm["tenant"], job.id)
    await execute_job(db_session, crm["tenant"], job.id)
    response = await client.get(
        f"/api/v1/operations/campaigns/{cid}/statistics", headers=crm["headers"]
    )
    assert response.json()["sent"] == 1, response.text
    assert response.json()["status"] == "completed"
    await dispatch_all(db_session, crm["tenant"])
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AnalyticsEvent)
            .where(AnalyticsEvent.event_type == "campaign.completed")
        )
        == 1
    )


async def test_campaign_suppression_checked_at_send_time(client, db_session, crm):
    cid = await prepare_campaign(client, crm)
    response = await post(client, crm, f"/operations/campaigns/{cid}/launch")
    assert response.status_code == 200, response.text
    crm["contact"].email_opted_out = True
    await db_session.flush()
    job = await db_session.scalar(
        select(OperationJob).where(OperationJob.kind == "campaign_send")
    )
    await execute_job(db_session, crm["tenant"], job.id)
    assert not crm["mock"].sent
    assert (
        await db_session.scalar(select(CampaignRecipient.status))
    ).value == "suppressed"


async def test_campaign_pause_and_sequence_order(client, db_session, crm):
    cid = await prepare_campaign(
        client,
        crm,
        [{"subject": "Follow up", "body": "Follow up body", "delay_hours": 0}],
    )
    await post(client, crm, f"/operations/campaigns/{cid}/launch")
    jobs = (
        await db_session.scalars(
            select(OperationJob)
            .where(OperationJob.kind == "campaign_send")
            .order_by(OperationJob.payload["step"].as_integer())
        )
    ).all()
    await post(client, crm, f"/operations/campaigns/{cid}/pause")
    await execute_job(db_session, crm["tenant"], jobs[0].id)
    assert not crm["mock"].sent
    await post(client, crm, f"/operations/campaigns/{cid}/resume")
    await execute_job(db_session, crm["tenant"], jobs[1].id)
    assert not crm["mock"].sent
    await execute_job(db_session, crm["tenant"], jobs[0].id)
    await execute_job(db_session, crm["tenant"], jobs[1].id)
    assert len(crm["mock"].sent) == 2


async def test_unknown_delivery_is_not_automatically_resent(client, db_session, crm):
    cid = await prepare_campaign(client, crm)
    await post(client, crm, f"/operations/campaigns/{cid}/launch")
    crm["mock"].failure = ProviderFailure("timeout", uncertain=True)
    job = await db_session.scalar(
        select(OperationJob).where(OperationJob.kind == "campaign_send")
    )
    await execute_job(db_session, crm["tenant"], job.id)
    assert job.status == "unknown"
    crm["mock"].failure = None
    await execute_job(db_session, crm["tenant"], job.id)
    assert not crm["mock"].sent


async def test_oauth_state_pkce_encryption_refresh_disconnect(client, db_session, crm):
    from urllib.parse import urlparse, parse_qs

    path = f"/operations/integrations/{crm['integration'].id}"
    started = await post(client, crm, path + "/authorize")
    assert started.status_code == 200, started.text
    params = parse_qs(urlparse(started.json()["authorization_url"]).query)
    assert params["code_challenge_method"] == ["S256"]
    data = {"state": params["state"][0], "code": "synthetic-code"}
    response = await post(client, crm, path + "/callback", data)
    assert response.status_code == 200, response.text
    assert "access_token" not in response.text
    repeat = await post(client, crm, path + "/callback", data)
    assert repeat.status_code == 400
    token = await db_session.scalar(select(OAuthToken))
    raw = await db_session.scalar(
        text("SELECT access_token FROM oauth_tokens WHERE id=:id"), {"id": token.id}
    )
    assert raw.startswith("enc:v1:")
    token.expires_at = now() - timedelta(seconds=1)
    await db_session.flush()
    response = await post(client, crm, path + "/refresh")
    assert response.status_code == 200, response.text
    assert crm["mock"].refreshes == 1
    response = await post(client, crm, path + "/disconnect")
    assert response.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(OAuthToken)) == 0


async def test_all_global_search_entities_are_indexed(client, db_session, crm):
    response = await client.get(
        "/api/v1/operations/search?q=Acme", headers=crm["headers"]
    )
    assert response.status_code == 200, response.text
    assert "companies" in {r["entity"] for r in response.json()["items"]}
    from app.core.search import PostgresSearch

    assert set(PostgresSearch.entities) == {
        "leads",
        "contacts",
        "companies",
        "deals",
        "tasks",
        "notes",
        "conversations",
        "messages",
        "campaigns",
        "agents",
    }


async def test_new_routes_enforce_viewer_permissions(client, db_session, crm):
    membership = await db_session.scalar(
        select(Membership).where(
            Membership.tenant_id == crm["tenant"], Membership.user_id == crm["user"]
        )
    )
    membership.role = RoleEnum.VIEWER
    await db_session.flush()
    for path in (
        "/operations/conversations",
        "/operations/workflows",
        "/operations/analytics/dashboard",
        "/operations/providers",
    ):
        response = await client.get("/api/v1" + path, headers=crm["headers"])
        assert response.status_code == 403, (path, response.text)


async def test_workflow_action_cannot_inject_privileges(client, crm):
    response = await post(
        client,
        crm,
        "/operations/workflows",
        {
            "name": "Invalid",
            "trigger": "lead.created",
            "actions": [
                {
                    "tool": "update_lead",
                    "arguments": {"entity_id": "$event.id", "tenant_id": str(uuid4())},
                }
            ],
        },
    )
    assert response.status_code == 422, response.text


async def test_idempotency_rejects_payload_reuse(client, db_session, crm):
    response = await post(
        client,
        crm,
        "/operations/conversations",
        {"subject": "Thread", "integration_id": str(crm["integration"].id)},
    )
    cid = response.json()["id"]
    first = await post(
        client,
        crm,
        f"/operations/conversations/{cid}/messages",
        {"recipient": "alice@example.com", "body": "A"},
    )
    second = await post(
        client,
        crm,
        f"/operations/conversations/{cid}/messages",
        {"recipient": "alice@example.com", "body": "B"},
    )
    assert first.status_code == 202 and second.status_code == 409
