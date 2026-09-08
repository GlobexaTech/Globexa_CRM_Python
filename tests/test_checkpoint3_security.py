"""Operational failure/retry, permission, tenant and provider contract boundaries."""

import asyncio
from datetime import timedelta
from uuid import uuid4, UUID
import pytest
from sqlalchemy import select, func, text
from fastapi import HTTPException
from app.models import (
    OperationJob,
    Membership,
    RoleEnum,
    Task,
    ExecutionLog,
    Lead,
    FeatureEntitlement,
    CampaignRecipient,
)
from app.services.crm.common import now
from app.services.crm.jobs import execute_job
from app.services.crm.providers import MailAdapter, UnavailableAdapter, ProviderFailure
from app.core.events import dispatch_event
from test_checkpoint3 import crm as crm, post, dispatch_all, prepare_campaign


async def test_redis7_rate_limit_is_atomic():
    from app.core.rate_limit import check_rate
    from app.core.config import get_settings
    from redis.asyncio import Redis

    redis = Redis.from_url(get_settings().redis.url)
    try:
        assert (await redis.info())["redis_version"].startswith("7.")
    finally:
        await redis.aclose()
    key = str(uuid4())
    results = await asyncio.gather(
        *(check_rate(key, limit=3) for _ in range(10)), return_exceptions=True
    )
    assert sum(r is None for r in results) == 3
    assert (
        sum(isinstance(r, HTTPException) and r.status_code == 429 for r in results) == 7
    )


async def test_new_model_columns_match_physical_database(db_session):
    from app.models import Base

    rows = (
        await db_session.execute(
            text(
                "SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public'"
            )
        )
    ).all()
    actual = set(rows)
    assert (
        not {(t.name, c.name) for t in Base.metadata.tables.values() for c in t.c}
        - actual
    )


@pytest.mark.parametrize("path", ["conversations", "workflows", "jobs", "integrations"])
async def test_foreign_ids_do_not_disclose_resources(client, crm, path):
    suffix = "/status" if path == "integrations" else ""
    response = await client.get(
        f"/api/v1/operations/{path}/{uuid4()}{suffix}", headers=crm["headers"]
    )
    assert response.status_code == 404, response.text


async def test_campaign_cross_tenant_enrollment_is_rejected(client, crm):
    response = await post(
        client,
        crm,
        "/campaigns",
        {"name": "Test", "sender_name": "Sales", "sender_email": "sales@example.com"},
    )
    cid = response.json()["id"]
    response = await post(
        client,
        crm,
        f"/operations/campaigns/{cid}/plan",
        {
            "integration_id": str(crm["integration"].id),
            "contact_ids": [str(crm["contact"].id), str(uuid4())],
            "subject": "Hi",
            "body": "Hi",
        },
        method="PUT",
    )
    assert response.status_code == 404


async def test_campaign_claim_rechecks_revoked_permissions(client, db_session, crm):
    cid = await prepare_campaign(client, crm)
    await post(client, crm, f"/operations/campaigns/{cid}/launch")
    member = await db_session.scalar(
        select(Membership).where(Membership.user_id == crm["user"])
    )
    member.role = RoleEnum.VIEWER
    await db_session.flush()
    job = await db_session.scalar(
        select(OperationJob).where(OperationJob.kind == "campaign_send")
    )
    await execute_job(db_session, crm["tenant"], job.id)
    assert job.status == "failed"
    assert not crm["mock"].sent


async def test_retry_after_explicit_provider_rejection_is_bounded(
    client, db_session, crm
):
    cid = await prepare_campaign(client, crm)
    await post(client, crm, f"/operations/campaigns/{cid}/launch")
    job = await db_session.scalar(
        select(OperationJob).where(OperationJob.kind == "campaign_send")
    )
    crm["mock"].failure = ProviderFailure("provider_http_429", retryable=True)
    for attempt in range(3):
        job.available_at = now() - timedelta(seconds=1)
        await db_session.flush()
        await execute_job(db_session, crm["tenant"], job.id)
    assert job.status == "failed" and job.attempts == 3
    assert not crm["mock"].sent


async def test_worker_crash_claim_is_not_resent(client, db_session, crm):
    cid = await prepare_campaign(client, crm)
    await post(client, crm, f"/operations/campaigns/{cid}/launch")
    job = await db_session.scalar(
        select(OperationJob).where(OperationJob.kind == "campaign_send")
    )
    job.status, job.claimed_at = "running", now() - timedelta(minutes=10)
    await db_session.flush()
    await execute_job(db_session, crm["tenant"], job.id)
    assert job.status == "unknown"
    assert not crm["mock"].sent


async def test_workflow_failure_rolls_back_earlier_actions_and_can_retry(
    client, db_session, crm
):
    data = {
        "name": "Atomic workflow",
        "trigger": "lead.created",
        "actions": [
            {
                "tool": "create_task",
                "arguments": {"title": "Must rollback", "lead_id": "$event.id"},
            },
            {
                "tool": "update_lead",
                "arguments": {"entity_id": str(uuid4()), "title": "Missing target"},
            },
        ],
    }
    response = await post(client, crm, "/operations/workflows", data)
    wid = response.json()["id"]
    await post(
        client,
        crm,
        f"/operations/workflows/{wid}/enabled",
        {"enabled": True},
        method="PATCH",
    )
    response = await post(client, crm, "/leads", {"title": "Trigger"})
    assert response.status_code == 201
    await dispatch_all(db_session, crm["tenant"])
    job = await db_session.scalar(
        select(OperationJob).where(OperationJob.kind == "automation")
    )
    await execute_job(db_session, crm["tenant"], job.id)
    assert job.status == "failed"
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Task).where(Task.title == "Must rollback")
        )
        == 0
    )
    log = await db_session.scalar(select(ExecutionLog))
    assert log.status == "failed" and log.attempts == 1
    response = await post(client, crm, f"/operations/jobs/{job.id}/retry")
    assert response.status_code == 202, response.text


async def test_workflow_version_snapshot_survives_edit(client, db_session, crm):
    data = {
        "name": "Versioned",
        "trigger": "lead.created",
        "actions": [
            {
                "tool": "create_task",
                "arguments": {"title": "Original action", "lead_id": "$event.id"},
            }
        ],
    }
    response = await post(client, crm, "/operations/workflows", data)
    wid = response.json()["id"]
    await post(
        client,
        crm,
        f"/operations/workflows/{wid}/enabled",
        {"enabled": True},
        method="PATCH",
    )
    await post(client, crm, "/leads", {"title": "Trigger"})
    await dispatch_all(db_session, crm["tenant"])
    data["actions"][0]["arguments"]["title"] = "New action"
    response = await post(
        client, crm, f"/operations/workflows/{wid}", data, method="PUT"
    )
    assert response.json()["version"] == 2
    assert response.json()["enabled"] is False
    await post(
        client,
        crm,
        f"/operations/workflows/{wid}/enabled",
        {"enabled": True},
        method="PATCH",
    )
    job = await db_session.scalar(
        select(OperationJob).where(OperationJob.kind == "automation")
    )
    await execute_job(db_session, crm["tenant"], job.id)
    assert (await db_session.scalar(select(Task.title))) == "Original action"


async def test_ai_request_requires_entitlement_and_batch_is_idempotent(
    client, db_session, crm
):
    lead = Lead(tenant_id=crm["tenant"], title="Scoring target")
    db_session.add(lead)
    await db_session.flush()
    data = {"requests": [{"capability": "lead_score", "entity_id": str(lead.id)}]}
    first = await post(client, crm, "/operations/ai/batches", data)
    repeat = await post(client, crm, "/operations/ai/batches", data)
    assert first.status_code == 202, first.text
    assert first.json()[0]["id"] == repeat.json()[0]["id"]
    rule = await db_session.scalar(
        select(FeatureEntitlement).where(FeatureEntitlement.feature_key == "ai_credits")
    )
    rule.enabled = False
    await db_session.flush()
    denied = await post(
        client,
        crm,
        "/operations/ai/requests",
        data["requests"][0],
        key="different-ai-request",
    )
    assert denied.status_code == 403


async def test_approved_tool_actions_are_idempotent(client, db_session, crm):
    data = {"arguments": {"title": "Tool task", "contact_id": str(crm["contact"].id)}}
    first = await post(client, crm, "/operations/tools/create_task", data)
    repeat = await post(client, crm, "/operations/tools/create_task", data)
    assert first.status_code == 200, first.text
    assert first.json() == repeat.json()
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Task).where(Task.title == "Tool task")
        )
        == 1
    )


async def test_signed_webhook_pipeline_queues_tenant_sync_once(client, db_session, crm):
    import hashlib, hmac, time
    from app.models import WebhookEndpoint

    secret = "synthetic-signature-fixture-value"
    # A generic signed bridge notification; no claim of Gmail Pub/Sub certification.
    crm["integration"].type = "webhook"
    endpoint = WebhookEndpoint(
        tenant_id=crm["tenant"],
        integration_id=crm["integration"].id,
        name="Webhook",
        url_path="/test",
        secret=secret,
    )
    db_session.add(endpoint)
    await db_session.flush()
    body, stamp = b'{"change":"inbox"}', str(int(time.time()))
    signature = hmac.new(
        secret.encode(), stamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    headers = {
        "X-Webhook-Timestamp": stamp,
        "X-Webhook-Signature": signature,
        "Content-Type": "application/json",
    }
    response = await client.post(
        f"/api/v1/hooks/{endpoint.id}", headers=headers, content=body
    )
    assert response.status_code == 202, response.text
    eid = UUID(response.json()["event_id"])
    await dispatch_event(db_session, eid)
    await dispatch_event(db_session, eid)
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(OperationJob)
            .where(OperationJob.kind == "sync")
        )
        == 1
    )


async def test_triggered_campaign_creates_one_recipient_per_contact(
    client, db_session, crm
):
    cid = await prepare_campaign(client, crm)
    response = await post(
        client,
        crm,
        f"/operations/campaigns/{cid}/plan",
        {
            "integration_id": str(crm["integration"].id),
            "contact_ids": [str(crm["contact"].id)],
            "subject": "Event",
            "body": "Triggered",
            "trigger_event": "lead.created",
        },
        method="PUT",
    )
    assert response.status_code == 200
    await post(client, crm, f"/operations/campaigns/{cid}/launch")
    for title in ("First", "Second"):
        await post(
            client,
            crm,
            "/leads",
            {"title": title, "contact_id": str(crm["contact"].id)},
        )
    await dispatch_all(db_session, crm["tenant"])
    assert (
        await db_session.scalar(select(func.count()).select_from(CampaignRecipient))
        == 1
    )


@pytest.mark.parametrize("provider", ["gmail", "outlook"])
async def test_mail_adapter_http_send_contract(provider):
    import httpx

    requests = []

    async def handle(request):
        requests.append(request)
        return (
            httpx.Response(200, json={"id": "provider-message", "threadId": "thread"})
            if provider == "gmail"
            else httpx.Response(202)
        )

    adapter = MailAdapter(provider, transport=httpx.MockTransport(handle))
    result = await adapter.send(
        "synthetic-access",
        {"recipient": "alice@example.com", "subject": "Contract", "body": "Test"},
        "job-1",
    )
    assert result["status"] == "sent"
    assert result["provider_message_id"] == (
        "provider-message" if provider == "gmail" else None
    )
    assert requests[0].url.host in {"gmail.googleapis.com", "graph.microsoft.com"}
    assert adapter.idempotent_send is False


async def test_unsupported_provider_does_not_claim_success():
    adapter = UnavailableAdapter()
    for capability in (
        "connect",
        "disconnect",
        "refresh",
        "health_check",
        "sync",
        "send",
        "handle_webhook",
    ):
        with pytest.raises(ProviderFailure, match="capability_unavailable"):
            await getattr(adapter, capability)()


async def test_unsubscribe_link_is_signed_idempotent_and_stops_campaign(
    client, db_session, crm
):
    from app.services.crm.unsubscribe import unsubscribe_url
    from urllib.parse import urlparse

    cid = await prepare_campaign(client, crm)
    await post(client, crm, f"/operations/campaigns/{cid}/launch")
    url = urlparse(unsubscribe_url(crm["tenant"], crm["contact"].id))
    response = await client.post(url.path + "?" + url.query)
    assert response.status_code == 200, response.text
    again = await client.post(url.path + "?" + url.query)
    assert again.status_code == 200
    job = await db_session.scalar(
        select(OperationJob).where(OperationJob.kind == "campaign_send")
    )
    await execute_job(db_session, crm["tenant"], job.id)
    assert not crm["mock"].sent
    invalid = await client.post(url.path + "?token=" + "x" * 30)
    assert invalid.status_code == 400


@pytest.mark.parametrize(
    "view", ["dashboard", "pipeline", "conversion", "campaigns", "activity", "ai"]
)
async def test_analytics_frontend_contracts(client, crm, view):
    response = await client.get(
        "/api/v1/operations/analytics/" + view, headers=crm["headers"]
    )
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), dict)


async def test_ai_hook_requires_explicit_approval(client, db_session, crm):
    await post(client, crm, "/leads", {"title": "New prospect"})
    await dispatch_all(db_session, crm["tenant"])
    hook = await db_session.scalar(
        select(OperationJob).where(OperationJob.kind == "ai_hook")
    )
    assert hook.status == "awaiting_approval"
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(OperationJob)
            .where(OperationJob.kind == "ai")
        )
        == 0
    )
    approved = await post(client, crm, f"/operations/jobs/{hook.id}/approve")
    assert approved.status_code == 202, approved.text
    repeat = await post(client, crm, f"/operations/jobs/{hook.id}/approve")
    assert approved.json()["id"] == repeat.json()["id"]


async def test_paused_schedule_resumes_without_losing_recipients(
    client, db_session, crm
):
    cid = await prepare_campaign(client, crm)
    await post(
        client,
        crm,
        f"/operations/campaigns/{cid}/schedule",
        {"scheduled_at": (now() + timedelta(hours=1)).isoformat()},
    )
    await post(client, crm, f"/operations/campaigns/{cid}/pause")
    response = await post(client, crm, f"/operations/campaigns/{cid}/resume")
    assert response.json()["status"] == "scheduled"


async def test_viewer_cannot_update_task_through_legacy_route(client, db_session, crm):
    task = Task(
        tenant_id=crm["tenant"], title="Protected task", contact_id=crm["contact"].id
    )
    db_session.add(task)
    member = await db_session.scalar(
        select(Membership).where(Membership.user_id == crm["user"])
    )
    member.role = RoleEnum.VIEWER
    await db_session.flush()
    response = await post(
        client, crm, f"/tasks/{task.id}", {"title": "Changed"}, method="PATCH"
    )
    assert response.status_code == 403


async def test_sales_executive_sees_newly_created_task(client, db_session, crm):
    member = await db_session.scalar(
        select(Membership).where(Membership.user_id == crm["user"])
    )
    member.role = RoleEnum.SALES_EXECUTIVE
    await db_session.flush()
    created = await post(
        client,
        crm,
        "/tasks",
        {"title": "My follow-up", "contact_id": str(crm["contact"].id)},
    )
    assert created.status_code == 201, created.text
    response = await client.get("/api/v1/tasks", headers=crm["headers"])
    assert response.status_code == 200, response.text
    assert any(row["id"] == created.json()["id"] for row in response.json()["items"])


async def test_analytics_permission_does_not_grant_underlying_module(
    client, db_session, crm, monkeypatch
):
    from app.core.rbac import ROLE_PERMISSIONS

    member = await db_session.scalar(
        select(Membership).where(Membership.user_id == crm["user"])
    )
    member.role = RoleEnum.MARKETING
    await db_session.flush()
    monkeypatch.setitem(ROLE_PERMISSIONS, RoleEnum.MARKETING, {"analytics:read"})
    response = await client.get(
        "/api/v1/operations/analytics/pipeline", headers=crm["headers"]
    )
    assert response.status_code == 403, response.text
