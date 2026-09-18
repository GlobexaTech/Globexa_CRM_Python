"""Actual PostgreSQL RLS under a restricted role, including pooled recovery."""

import asyncio
import os
from contextlib import nullcontext
from uuid import uuid4
import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.core.config import get_settings
from app.core.tenant_context import tenant_context
from app.core.runtime_security import verify_runtime_security
from app.models import (
    Tenant,
    User,
    Membership,
    Contact,
    Integration,
    DomainEvent,
    AuditLog,
    UsageRecord,
    AgentExecution,
    AgentMemory,
    ApprovalRequest,
    SyncJob,
    SyncCursor,
    DeadLetterEvent,
)

MODELS = (
    Contact,
    AgentExecution,
    AgentMemory,
    ApprovalRequest,
    SyncJob,
    SyncCursor,
    DeadLetterEvent,
)


def values(model, tenant, user, integration):
    fields = {
        Contact: {"first_name": "RLS", "last_name": "Probe"},
        AgentExecution: {
            "actor_id": user,
            "agent_name": "research",
            "task_type": "research",
            "idempotency_key": str(uuid4()),
        },
        AgentMemory: {
            "actor_id": user,
            "agent_name": "research",
            "memory_type": "working",
            "key": str(uuid4()),
            "value": {},
        },
        ApprovalRequest: {
            "requesting_user_id": user,
            "agent_name": "sales",
            "action_type": "create_task",
            "proposed_action": {},
            "action_hash": "0" * 64,
            "idempotency_key": str(uuid4()),
        },
        SyncJob: {"integration_id": integration, "sync_type": "initial"},
        SyncCursor: {
            "integration_id": integration,
            "cursor_type": str(uuid4()),
            "cursor_value": "server-cursor",
        },
        DeadLetterEvent: {"provider": "gmail", "event_type": "test", "payload": {}},
    }
    return {"tenant_id": tenant, **fields[model]}


@pytest_asyncio.fixture
async def isolated_rls():
    admin = create_async_engine(get_settings().database.url, poolclass=NullPool)
    url = make_url(get_settings().database.url).set(
        username=os.environ.get("RUNTIME_DATABASE_ROLE", "globexa_runtime"),
        password=os.environ["RUNTIME_DATABASE_PASSWORD"],
    )
    runtime = create_async_engine(url, pool_size=1, max_overflow=0)
    factory = async_sessionmaker(runtime, expire_on_commit=False)
    tenants, users, integrations = ([uuid4(), uuid4()] for _ in range(3))
    rows = {}
    try:
        async with async_sessionmaker(admin, expire_on_commit=False)() as db:
            for i in range(2):
                db.add(Tenant(id=tenants[i], name="RLS fixture", slug=str(tenants[i])))
                db.add(
                    User(
                        id=users[i],
                        email=f"{users[i]}@example.test",
                        hashed_password="test-only",
                        full_name="RLS fixture",
                    )
                )
            await db.flush()
            for i in range(2):
                db.add(Membership(tenant_id=tenants[i], user_id=users[i], role="owner"))
                db.add(
                    Integration(
                        id=integrations[i],
                        tenant_id=tenants[i],
                        name="RLS fixture",
                        type="email_inbox",
                        created_by_id=users[i],
                    )
                )
            await db.flush()
            for model in MODELS:
                rows[model] = []
                for i in range(2):
                    row = model(**values(model, tenants[i], users[i], integrations[i]))
                    db.add(row)
                    await db.flush()
                    rows[model].append(row.id)
            await db.commit()
        async with factory() as db:
            role = (
                await db.execute(
                    text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")
                )
            ).one()
            assert role == (False, False)
            await verify_runtime_security(db)
        yield factory, tenants, users, integrations, rows
    finally:
        await runtime.dispose()
        async with admin.begin() as db:
            for model in (
                AuditLog,
                UsageRecord,
                *reversed(MODELS),
                DomainEvent,
                Integration,
                Membership,
            ):
                await db.execute(delete(model).where(model.tenant_id.in_(tenants)))
            await db.execute(delete(Tenant).where(Tenant.id.in_(tenants)))
            await db.execute(delete(User).where(User.id.in_(users)))
        await admin.dispose()


async def test_rls_catalog_all_tenant_tables_and_crud_policy_coverage(isolated_rls):
    factory, *_ = isolated_rls
    async with factory() as db:
        rows = (
            (
                await db.execute(
                    text("""
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   array_agg(p.polcmd::text) AS commands,
                   bool_or(NOT p.polpermissive AND p.polcmd='*') AS mandatory_guard
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_policy p ON p.polrelid=c.oid
            WHERE n.nspname='public' AND c.relkind='r'
              AND EXISTS(SELECT 1 FROM information_schema.columns x
                         WHERE x.table_schema=n.nspname AND x.table_name=c.relname AND x.column_name='tenant_id')
            GROUP BY c.oid,c.relname,c.relrowsecurity,c.relforcerowsecurity
        """)
                )
            )
            .mappings()
            .all()
        )
        assert len(rows) >= 60
        assert {m.__tablename__ for m in MODELS} <= {r["relname"] for r in rows}
        for row in rows:
            assert row["relrowsecurity"] and row["relforcerowsecurity"], row["relname"]
            assert "*" in row["commands"] or {"r", "a", "w", "d"} <= set(row["commands"]), row[
                "relname"
            ]
            if row["relname"] != "memberships":
                assert row["mandatory_guard"], row["relname"]
        assert not await db.scalar(
            text(
                "SELECT has_table_privilege(current_user,'audit_logs','UPDATE') OR has_table_privilege(current_user,'audit_logs','DELETE')"
            )
        )


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__tablename__)
async def test_bidirectional_select_insert_update_delete_and_default_deny(isolated_rls, model):
    factory, tenants, users, integrations, rows = isolated_rls
    for i in range(2):
        other = 1 - i
        with tenant_context(tenants[i], users[i]):
            async with factory() as db:
                await db.execute(text("SELECT set_config('app.is_admin','true',true)"))
                assert set(await db.scalars(select(model.id))) == {rows[model][i]}
                assert (
                    await db.execute(
                        update(model)
                        .where(model.id == rows[model][other])
                        .values(tenant_id=tenants[i])
                    )
                ).rowcount == 0
                assert (
                    await db.execute(delete(model).where(model.id == rows[model][other]))
                ).rowcount == 0
                assert (
                    await db.execute(
                        update(model).where(model.id == rows[model][i]).values(tenant_id=tenants[i])
                    )
                ).rowcount == 1
                assert (
                    await db.execute(delete(model).where(model.id == rows[model][i]))
                ).rowcount == 1
                await db.rollback()
                db.add(model(**values(model, tenants[i], users[i], integrations[i])))
                await db.flush()
                await db.rollback()
            async with factory() as db:
                db.add(model(**values(model, tenants[other], users[other], integrations[other])))
                with pytest.raises(DBAPIError) as error:
                    await db.flush()
                assert "row-level security" in str(error.value).lower()
                await db.rollback()
            async with factory() as db:
                with pytest.raises(DBAPIError) as error:
                    await db.execute(
                        update(model)
                        .where(model.id == rows[model][i])
                        .values(tenant_id=tenants[other])
                    )
                assert "row-level security" in str(error.value).lower()
                await db.rollback()
    async with factory() as db:
        assert list(await db.scalars(select(model.id))) == []
        assert (await db.execute(update(model).values(tenant_id=tenants[0]))).rowcount == 0
        assert (await db.execute(delete(model))).rowcount == 0
        db.add(model(**values(model, tenants[0], users[0], integrations[0])))
        with pytest.raises(DBAPIError) as error:
            await db.flush()
        assert "row-level security" in str(error.value).lower()
        await db.rollback()


async def test_pool_reuse_rollback_exception_timeout_and_concurrent_tenants(isolated_rls):
    factory, tenants, users, _, rows = isolated_rls
    pids = []

    async def probe(index, failure=None):
        context = (
            tenant_context(tenants[index], users[index]) if index is not None else nullcontext()
        )
        with context:
            async with factory() as db:
                pids.append(await db.scalar(text("SELECT pg_backend_pid()")))
                assert set(await db.scalars(select(Contact.id))) == (
                    {rows[Contact][index]} if index is not None else set()
                )
                if failure == "timeout":
                    await db.execute(text("SET LOCAL statement_timeout = '15ms'"))
                    with pytest.raises(DBAPIError):
                        await db.execute(text("SELECT pg_sleep(0.1)"))
                    await db.rollback()
                elif failure == "exception":
                    with pytest.raises(ValueError):
                        try:
                            raise ValueError("transaction abort")
                        finally:
                            await db.rollback()
                else:
                    await db.commit()
                assert set(await db.scalars(select(Contact.id))) == (
                    {rows[Contact][index]} if index is not None else set()
                )

    for index, failure in [
        (0, None),
        (1, "exception"),
        (None, None),
        (0, "timeout"),
        (1, None),
        (0, None),
    ]:
        await probe(index, failure)
    await asyncio.gather(*(probe(i % 2) for i in range(12)))
    await probe(None)
    assert len(set(pids)) == 1, "All probes must reuse the same physical connection"


async def test_new_foreign_keys_reject_cross_tenant_parents(isolated_rls):
    factory, tenants, users, integrations, rows = isolated_rls
    for model, foreign in [
        (AgentExecution, {"parent_id": rows[AgentExecution][1]}),
        (AgentMemory, {"execution_id": rows[AgentExecution][1]}),
        (ApprovalRequest, {"execution_id": rows[AgentExecution][1]}),
        (SyncJob, {"integration_id": integrations[1]}),
        (SyncCursor, {"integration_id": integrations[1]}),
    ]:
        with tenant_context(tenants[0], users[0]):
            async with factory() as db:
                db.add(model(**{**values(model, tenants[0], users[0], integrations[0]), **foreign}))
                with pytest.raises(DBAPIError) as error:
                    await db.flush()
                assert "foreign key" in str(error.value).lower()
                await db.rollback()
