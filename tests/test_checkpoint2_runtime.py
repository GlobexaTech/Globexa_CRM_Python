"""Connection reuse, worker execution, webhook delivery and foundation API tests."""
import asyncio
import hashlib
import hmac
import json
import os
import time
from uuid import uuid4
import pytest
from sqlalchemy import select, text, delete, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.core.tenant_context import tenant_context
from app.models import Tenant, Contact, DomainEvent, WebhookEndpoint, Integration, WebhookReceipt, AuditLog


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    monkeypatch.setattr(get_settings().security, "credential_encryption_key", Fernet.generate_key().decode())


async def test_pool_reuse_transaction_commit_and_rollback():
    settings = get_settings()
    admin = create_async_engine(settings.database.url, poolclass=NullPool)
    runtime_url = make_url(settings.database.url).set(username="globexa_runtime",
                      password=os.environ.get("RUNTIME_DATABASE_PASSWORD", "checkpoint2-local-isolated-test"))
    runtime = create_async_engine(runtime_url, pool_size=1, max_overflow=0)
    ids = [uuid4(), uuid4()]
    try:
        async with async_sessionmaker(admin, expire_on_commit=False)() as db:
            db.add_all([Tenant(id=i, name="Pool probe", slug=str(i)) for i in ids])
            await db.flush()
            db.add_all([Contact(tenant_id=i, first_name="Pool", last_name="Probe") for i in ids])
            await db.commit()
        pids = []
        for tenant in [ids[0], ids[1], None, ids[0]]:
            context = tenant_context(tenant) if tenant else None
            if context:
                context.__enter__()
            try:
                async with async_sessionmaker(runtime)() as db:
                    pids.append(await db.scalar(text("SELECT pg_backend_pid()")))
                    rows = (await db.scalars(select(Contact.tenant_id))).all()
                    assert rows == ([tenant] if tenant else [])
                    await db.commit()
                    # Explicit commits must reapply context for the next transaction.
                    assert (await db.scalars(select(Contact.tenant_id))).all() == rows
                    await db.rollback()
            finally:
                if context:
                    context.__exit__(None, None, None)
        assert len(set(pids)) == 1, "Test must reuse one physical PostgreSQL connection"
    finally:
        async with admin.begin() as conn:
            for table in (DomainEvent.__table__, Contact.__table__):
                await conn.execute(delete(table).where(table.c.tenant_id.in_(ids)))
            await conn.execute(delete(Tenant).where(Tenant.id.in_(ids)))
        await runtime.dispose()
        await admin.dispose()


def test_real_celery_task_uses_tenant_context(monkeypatch):
    from app.workers.tasks.usage_tasks import record_usage
    from app.models import UsageRecord
    settings = get_settings()
    admin_url = settings.database.url
    tenant_ids = [uuid4(), uuid4()]
    async def seed():
        engine = create_async_engine(admin_url, poolclass=NullPool)
        async with async_sessionmaker(engine)() as db:
            db.add_all([Tenant(id=i, name="Worker probe", slug=str(i)) for i in tenant_ids])
            await db.commit()
        await engine.dispose()
    asyncio.run(seed())
    monkeypatch.setattr(settings.database, "username", "globexa_runtime")
    monkeypatch.setattr(settings.database, "password", os.environ.get("RUNTIME_DATABASE_PASSWORD", "checkpoint2-local-isolated-test"))
    try:
        for tenant in tenant_ids:
            result = record_usage.apply(kwargs={"tenant_id": str(tenant), "metric": "worker_test", "quantity": 1}, throw=True)
            assert result.result == {"status": "recorded"}
        async def verify():
            from app.core.tenant_context import tenant_db_context
            for tenant in tenant_ids:
                async with tenant_db_context(tenant) as db:
                    assert (await db.scalars(select(UsageRecord.tenant_id))).all() == [tenant]
        asyncio.run(verify())
    finally:
        async def cleanup():
            engine = create_async_engine(admin_url, poolclass=NullPool)
            async with engine.begin() as conn:
                await conn.execute(delete(UsageRecord).where(UsageRecord.tenant_id.in_(tenant_ids)))
                await conn.execute(delete(AuditLog).where(AuditLog.tenant_id.in_(tenant_ids)))
                await conn.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
            await engine.dispose()
        asyncio.run(cleanup())


async def test_webhook_durable_idempotency(client, db_session, test_tenant, test_user):
    item = Integration(tenant_id=test_tenant.id, type="webhook", name="Ingress", created_by_id=test_user.id)
    db_session.add(item)
    await db_session.flush()
    secret = "a" * 32
    endpoint = WebhookEndpoint(tenant_id=test_tenant.id, integration_id=item.id,
                              name="Test", url_path="/probe", secret=secret)
    db_session.add(endpoint)
    await db_session.flush()
    body = json.dumps({"message": "signed", "tenant_id": str(uuid4())}).encode()
    stamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), stamp.encode()+b"."+body, hashlib.sha256).hexdigest()
    await db_session.execute(text("SET LOCAL ROLE globexa_runtime"))
    for expected in ("accepted", "duplicate"):
        response = await client.post(f"/api/v1/hooks/{endpoint.id}", content=body,
                                      headers={"X-Webhook-Timestamp": stamp, "X-Webhook-Signature": signature})
        assert response.status_code == 202, response.text
        assert response.json()["status"] == expected
    receipts = (await db_session.scalars(select(WebhookReceipt))).all()
    assert len(receipts) == 1
    assert receipts[0].tenant_id == test_tenant.id
    event = await db_session.get(DomainEvent, receipts[0].event_id)
    assert event.tenant_id == test_tenant.id
    assert event.published_at is None


async def test_oauth_tokens_never_returned(client, auth_headers, db_session, test_user, test_tenant):
    item = Integration(tenant_id=test_tenant.id, type="webhook", name="OAuth", created_by_id=test_user.id)
    db_session.add(item)
    await db_session.flush()
    response = await client.post("/api/v1/foundation/oauth-tokens", headers=auth_headers, json={
        "integration_id": str(item.id), "access_token": "sensitive-token", "refresh_token": "sensitive-refresh"})
    assert response.status_code == 201
    assert "sensitive" not in response.text
    stored = await db_session.scalar(text("SELECT access_token FROM oauth_tokens WHERE id=:id"), {"id": response.json()["id"]})
    assert stored.startswith("enc:v1:")


async def test_workflow_foundation_stays_inactive(client, auth_headers, db_session):
    from app.models import Workflow, Trigger, Condition, Action
    response = await client.post("/api/v1/foundation/workflows", headers=auth_headers, json={
        "name": "Lead review", "trigger": "lead.created", "condition": {"field": "status", "operator": "eq", "value": "new"},
        "tool": "lead.read"})
    assert response.status_code == 201, response.text
    assert response.json()["enabled"] is False
    for model in [Workflow, Trigger, Condition, Action]:
        assert await db_session.scalar(select(func.count()).select_from(model)) == 1


async def test_outbox_broker_failure_retries_without_losing_event(db_session, test_tenant):
    from app.core.events import publish_event, drain_outbox
    item = publish_event(db_session, tenant_id=test_tenant.id, event_type="lead.created", aggregate_id=uuid4())
    await db_session.flush()
    class Offline:
        async def publish(self, *args):
            raise ConnectionError("Broker offline")
    with pytest.raises(ConnectionError):
        await drain_outbox(db_session, Offline())
    assert item.published_at is None
    seen = []
    class Online:
        async def publish(self, *args):
            seen.append(args)
    assert await drain_outbox(db_session, Online()) == 1
    assert seen == [(str(item.id), str(test_tenant.id))]


async def test_ai_tool_permission_rechecks_crm_api(client, auth_headers, test_tenant, test_user, db_session):
    from app.services.ai.tools import ToolPermissionLayer
    from app.models import Membership
    from sqlalchemy import update
    token = auth_headers["Authorization"].removeprefix("Bearer ")
    tools = ToolPermissionLayer(client)
    with pytest.raises(PermissionError):
        await tools.execute("sql.execute", {}, token=token, tenant_id=test_tenant.id, approved_tools={"sql.execute"})
    await db_session.execute(update(Membership).where(Membership.user_id == test_user.id).values(role="viewer"))
    import httpx
    with pytest.raises(httpx.HTTPStatusError):
        await tools.execute("lead.create", {"title": "denied"}, token=token, tenant_id=test_tenant.id, approved_tools={"lead.create"})
