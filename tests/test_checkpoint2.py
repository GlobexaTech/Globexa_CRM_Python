"""Executed security regressions; PostgreSQL with a real restricted runtime role."""
import hashlib
import hmac
import json
import os
import time
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text, func, update, delete
from sqlalchemy.exc import DBAPIError

from app.core.credentials import CredentialService
from app.core.tenant_context import bind_context, tenant_context, current_tenant
from app.core.webhooks import verify_signature, InvalidWebhook
from app.models import Base, Lead, Contact, Tenant, Integration, IntegrationCredential, DomainEvent, AuditLog


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings().security, "credential_encryption_key", Fernet.generate_key().decode())


async def restrict(db, tenant_id=None, user_id=None):
    await db.execute(text("SET LOCAL ROLE globexa_runtime"))
    await bind_context(db, tenant_id, user_id)
    assert not await db.scalar(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user"))


async def seed_two(db, test_tenant):
    other = Tenant(name="Other", slug=f"other-{uuid4()}")
    db.add(other)
    await db.flush()
    own = Contact(tenant_id=test_tenant.id, first_name="Own", last_name="Contact", email="own@example.com")
    foreign = Contact(tenant_id=other.id, first_name="Foreign", last_name="Contact", email="foreign@example.com")
    db.add_all([own, foreign])
    await db.flush()
    a = Lead(tenant_id=test_tenant.id, title="Own lead", contact_id=own.id)
    b = Lead(tenant_id=other.id, title="Foreign lead", contact_id=foreign.id)
    db.add_all([a, b])
    await db.flush()
    return other, own, foreign, a, b


async def test_rls_inventory_matches_metadata(db_session):
    expected = {t.name for t in Base.metadata.tables.values() if "tenant_id" in t.c} | {"users", "tenants"}
    rows = (await db_session.execute(text("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r'"))).all()
    actual = {name for name, enabled, forced in rows if enabled and forced}
    assert expected == actual
    policies = (await db_session.execute(text("SELECT tablename, policyname, qual, with_check FROM pg_policies WHERE schemaname='public'"))).all()
    assert len({(row[0], row[1]) for row in policies}) == len(policies)
    for table in expected - {"users", "tenants", "audit_logs", "memberships"}:
        policy = next(row for row in policies if row[0] == table)
        assert policy[2] and policy[3]


async def test_unfiltered_orm_join_aggregate(db_session, test_tenant):
    other, own, foreign, a, b = await seed_two(db_session, test_tenant)
    await restrict(db_session, test_tenant.id)
    assert (await db_session.scalars(select(Lead.id))).all() == [a.id]
    assert await db_session.scalar(select(func.count()).select_from(Lead)) == 1
    rows = (await db_session.execute(select(Lead.title, Contact.first_name).join(Contact))).all()
    assert rows == [("Own lead", "Own")]
    await db_session.execute(update(Lead).where(Lead.id == a.id).values(title="Updated"))
    assert await db_session.scalar(select(Lead.title)) == "Updated"
    assert (await db_session.execute(update(Lead).where(Lead.id == b.id).values(title="stolen"))).rowcount == 0
    assert (await db_session.execute(delete(Lead).where(Lead.id == b.id))).rowcount == 0
    assert (await db_session.execute(delete(Lead).where(Lead.id == a.id))).rowcount == 1


async def test_rls_missing_context_denies_rows(db_session, test_tenant):
    await seed_two(db_session, test_tenant)
    await restrict(db_session)
    assert (await db_session.scalars(select(Lead))).all() == []


async def test_rls_rejects_foreign_insert(db_session, test_tenant):
    other, *_ = await seed_two(db_session, test_tenant)
    await restrict(db_session, test_tenant.id)
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            db_session.add(Lead(tenant_id=other.id, title="Attack"))
            await db_session.flush()


async def test_rls_rejects_tenant_reassignment(db_session, test_tenant):
    other, own, foreign, a, b = await seed_two(db_session, test_tenant)
    await restrict(db_session, test_tenant.id)
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(update(Lead).where(Lead.id == a.id).values(tenant_id=other.id))


async def test_composite_fk_rejects_foreign_parent(db_session, test_tenant):
    other, own, foreign, a, b = await seed_two(db_session, test_tenant)
    await restrict(db_session, test_tenant.id)
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            db_session.add(Lead(tenant_id=test_tenant.id, title="Bad join", contact_id=foreign.id))
            await db_session.flush()


async def test_ciphertext_at_rest_and_transparent_worker_read(db_session, test_tenant, test_user):
    item = Integration(tenant_id=test_tenant.id, type="apollo", name="Test", created_by_id=test_user.id)
    db_session.add(item)
    await db_session.flush()
    cred = IntegrationCredential(tenant_id=test_tenant.id, integration_id=item.id, name="key",
                                 credentials_encrypted=json.dumps({"api_key": "sensitive-provider-key"}),
                                 access_token="oauth-sensitive", refresh_token="refresh-sensitive")
    db_session.add(cred)
    await db_session.flush()
    raw = (await db_session.execute(text("SELECT credentials_encrypted, access_token, refresh_token FROM integration_credentials WHERE id=:id"), {"id": cred.id})).one()
    assert all(value.startswith("enc:v1:") and "sensitive" not in value for value in raw)
    db_session.expire(cred)
    await db_session.refresh(cred)
    assert json.loads(cred.credentials_encrypted)["api_key"] == "sensitive-provider-key"
    assert cred.access_token == "oauth-sensitive"


def test_encryption_tamper_and_wrong_key():
    service = CredentialService(Fernet.generate_key())
    value = service.encrypt("provider-key")
    assert service.decrypt(value) == "provider-key"
    for bad in ("plaintext", value[:-8] + "tampered"):
        with pytest.raises(ValueError):
            service.decrypt(bad)
    with pytest.raises(ValueError):
        CredentialService(Fernet.generate_key()).decrypt(value)


@pytest.mark.parametrize("provider", ["meta", "facebook", "instagram", "whatsapp", "generic", "stripe"])
def test_signed_provider_webhooks(provider):
    secret = "a" * 32
    now = int(time.time())
    body = json.dumps({"entry": [{"time": now}]}).encode()
    if provider in {"meta", "facebook", "instagram", "whatsapp"}:
        headers = {"X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}
    else:
        sig = hmac.new(secret.encode(), str(now).encode() + b"." + body, hashlib.sha256).hexdigest()
        headers = {"Stripe-Signature": f"t={now},v1={sig}"} if provider == "stripe" else {"X-Webhook-Timestamp": str(now), "X-Webhook-Signature": sig}
    assert verify_signature(provider, secret, body, headers, now) == hashlib.sha256(body).hexdigest()
    with pytest.raises(InvalidWebhook):
        verify_signature(provider, secret, body + b" ", headers, now)
    with pytest.raises(InvalidWebhook):
        verify_signature(provider, secret, body, headers, now + 301)
    with pytest.raises(InvalidWebhook):
        verify_signature(provider, secret, body, {}, now)


@pytest.mark.parametrize("field,value", [("tenant_id", str(uuid4())), ("is_superuser", True),
                                         ("permissions", ["*"]), ("created_at", "2026-01-01"), ("role", "owner")])
async def test_profile_rejects_protected_fields(client, auth_headers, field, value):
    response = await client.patch("/api/v1/auth/me", headers=auth_headers, json={field: value})
    assert response.status_code == 422


async def test_manager_cannot_create_owner(client, auth_headers, test_user, test_tenant, db_session):
    from app.models import Membership
    await db_session.execute(update(Membership).where(Membership.user_id == test_user.id).values(role="sales_manager"))
    response = await client.post("/api/v1/users", headers=auth_headers, json={
        "email": "new-owner@example.com", "password": "strong-password", "full_name": "Owner", "role": "owner"})
    assert response.status_code == 403


async def test_admin_cannot_promote_self(client, auth_headers, test_user, db_session):
    from app.models import Membership
    await db_session.execute(update(Membership).where(Membership.user_id == test_user.id).values(role="admin"))
    response = await client.patch(f"/api/v1/users/{test_user.id}/memberships", headers=auth_headers, json={"role": "owner"})
    assert response.status_code == 403


async def test_runtime_auth_and_identity_rls(client, test_user, test_tenant, db_session):
    await restrict(db_session)
    assert (await db_session.execute(text("SELECT id FROM users"))).all() == []
    response = await client.post("/api/v1/auth/login", data={"username": test_user.email, "password": "password"})
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}", "X-Tenant-ID": str(test_tenant.id)}
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200


async def test_outbox_rollback_and_audit_immutable(db_session, test_tenant):
    await restrict(db_session, test_tenant.id)
    async with db_session.begin_nested() as tx:
        db_session.add(Lead(tenant_id=test_tenant.id, title="Atomic"))
        await db_session.flush()
        assert await db_session.scalar(select(func.count()).select_from(DomainEvent)) == 1
        await tx.rollback()
    assert await db_session.scalar(select(func.count()).select_from(DomainEvent)) == 0
    audit = AuditLog(tenant_id=test_tenant.id, action="test", resource_type="test", new_values={"password": "hidden"})
    db_session.add(audit)
    await db_session.flush()
    assert audit.new_values == {"password": "[redacted]"}
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(delete(AuditLog))


async def test_search_is_tenant_scoped(db_session, test_tenant):
    from app.core.search import PostgresSearch
    await seed_two(db_session, test_tenant)
    await restrict(db_session, test_tenant.id)
    search = PostgresSearch(db_session)
    assert len(await search.search(test_tenant.id, "leads", "Own")) == 1
    assert await search.search(test_tenant.id, "leads", "Foreign") == []


async def test_entitlement_limit(db_session, test_tenant):
    from app.core.entitlements import EntitlementService, EntitlementDenied
    from app.models import FeatureEntitlement
    db_session.add(FeatureEntitlement(tenant_id=test_tenant.id, feature_key="ai_credits", enabled=True, limit_value=1))
    await db_session.flush()
    await restrict(db_session, test_tenant.id)
    service = EntitlementService(db_session)
    await service.consume(test_tenant.id, "ai_credits")
    with pytest.raises(EntitlementDenied):
        await service.consume(test_tenant.id, "ai_credits")


async def test_ai_fallback_records_every_attempt():
    from app.services.ai.gateway import AIGateway, ModelRoute, Generation
    from app.models import AITaskTypeEnum, AIUsageLog
    from app.core.config import get_settings
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    engine = create_async_engine(get_settings().database.url, poolclass=NullPool)
    tenant_id = uuid4()
    class Failed:
        async def generate(self, model, **kwargs):
            raise RuntimeError("do not store provider secret")
    class Working:
        async def generate(self, model, **kwargs):
            return Generation("result", 10, 5)
    try:
        async with async_sessionmaker(engine)() as db:
            db.add(Tenant(id=tenant_id, name="AI probe", slug=str(tenant_id)))
            await db.commit()
        async with async_sessionmaker(engine)() as db:
            gateway = AIGateway({"deepseek": Failed(), "nvidia": Working()},
                [ModelRoute("deepseek", "first"), ModelRoute("nvidia", "second")])
            result = await gateway.execute(db, tenant_id, None, AITaskTypeEnum.CLASSIFICATION, "generate", prompt="test")
            assert result.content == "result"
            await db.rollback()
            # All failures must also survive request rollback.
            with pytest.raises(RuntimeError):
                await AIGateway({"deepseek": Failed()}, [ModelRoute("deepseek", "first")]).execute(
                    db, tenant_id, None, AITaskTypeEnum.CLASSIFICATION, "generate", prompt="test")
            await db.rollback()
            rows = (await db.scalars(select(AIUsageLog).where(AIUsageLog.tenant_id == tenant_id))).all()
            assert len(rows) == 3
            assert {row.success for row in rows} == {False, True}
            assert all("secret" not in (row.error_message or "") for row in rows)
    finally:
        async with engine.begin() as conn:
            await conn.execute(delete(AIUsageLog).where(AIUsageLog.tenant_id == tenant_id))
            await conn.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant_id))
            await conn.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await engine.dispose()


def test_worker_registry_requires_tenants():
    import inspect
    from app.workers.celery_app import celery_app
    celery_app.loader.import_default_modules()
    for name, task in celery_app.tasks.items():
        if name.startswith("app.workers.") and not name.endswith("dispatch_scheduled"):
            assert "tenant_id" in inspect.signature(task.run).parameters, name


def test_context_reset_on_error():
    with pytest.raises(RuntimeError):
        with tenant_context(uuid4()):
            assert current_tenant.get() is not None
            raise RuntimeError("test")
    assert current_tenant.get() is None


async def test_disabled_identity_cannot_reach_tenant_only_route(client, auth_headers, test_user, db_session):
    from app.models import User
    await db_session.execute(update(User).where(User.id == test_user.id).values(is_active=False))
    response = await client.get("/api/v1/tenants/me", headers=auth_headers)
    assert response.status_code == 403


async def test_tenant_admin_cannot_create_global_superuser(client, auth_headers):
    response = await client.post("/api/v1/users", headers=auth_headers, json={
        "email": "super@example.com", "password": "strong-password", "full_name": "Attempt", "is_superuser": True})
    assert response.status_code == 422


def test_peer_roles_do_not_inherit_ai_permissions():
    from app.core.rbac import get_role_permissions
    from app.models import RoleEnum
    assert "ai:chat" not in get_role_permissions(RoleEnum.VIEWER)
    assert "leads:write" not in get_role_permissions(RoleEnum.AI_AGENT)


async def test_runtime_registration_uses_narrow_bootstrap(client, db_session):
    await restrict(db_session)
    response = await client.post("/api/v1/auth/register", json={
        "email": "runtime-register@example.com", "password": "strong-password", "full_name": "Runtime"})
    assert response.status_code == 201, response.text


def test_nested_camelcase_secrets_are_detected():
    from app.core.input_security import contains_secrets, redact
    data = {"nested": [{"apiKey": "hidden", "client-secret": "hidden"}]}
    assert contains_secrets(data)
    assert "hidden" not in json.dumps(redact(data))


async def test_production_runtime_rejects_privileged_role(db_session):
    from app.core.runtime_security import verify_runtime_security
    with pytest.raises(RuntimeError, match="SUPERUSER"):
        await verify_runtime_security(db_session)
    await restrict(db_session)
    await verify_runtime_security(db_session)


async def test_production_runtime_rejects_unprotected_table(db_session):
    from app.core.runtime_security import verify_runtime_security
    await db_session.execute(text("ALTER TABLE leads NO FORCE ROW LEVEL SECURITY"))
    await restrict(db_session)
    with pytest.raises(RuntimeError, match="migrations are incomplete"):
        await verify_runtime_security(db_session)
