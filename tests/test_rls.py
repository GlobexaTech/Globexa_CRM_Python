"""Executable PostgreSQL RLS isolation tests.

These tests deliberately assert positive visibility, negative cross-tenant
access, write enforcement, transaction scoping, and catalog coverage. They
must fail when the test role bypasses RLS.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import tenant_context
from app.models import Contact, Membership, Tenant, User


async def _assert_test_role_does_not_bypass_rls(db: AsyncSession) -> None:
    row = (await db.execute(text(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ))).one()
    assert row.rolsuper is False, "RLS tests require a non-superuser database role."
    assert row.rolbypassrls is False, "RLS tests require a NOBYPASSRLS database role."


async def _create_identity(db: AsyncSession, label: str):
    suffix = uuid4().hex[:12]
    tenant = Tenant(name=f"Tenant {label}", slug=f"rls-{label.lower()}-{suffix}", is_active=True)
    user = User(
        email=f"rls-{label.lower()}-{suffix}@example.test",
        hashed_password="test-only",
        full_name=f"RLS User {label}",
        is_active=True,
    )
    db.add_all([tenant, user])
    await db.flush()
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, role="owner", is_default=True))
    await db.commit()
    return tenant, user


async def _create_contact(db: AsyncSession, tenant: Tenant, user: User, label: str):
    contact = Contact(
        tenant_id=tenant.id,
        first_name="RLS",
        last_name=label,
        email=f"{label.lower()}-{uuid4().hex[:10]}@example.test",
        created_by_id=user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(contact)
    await db.commit()
    return contact


@pytest.mark.asyncio
async def test_rls_catalog_coverage(db_session: AsyncSession):
    """Every tenant_id base table must have RLS and FORCE RLS plus a policy."""
    await _assert_test_role_does_not_bypass_rls(db_session)
    rows = (await db_session.execute(text("""
        SELECT c.relname AS table_name,
               c.relrowsecurity AS rls_enabled,
               c.relforcerowsecurity AS force_rls,
               count(p.oid) AS policy_count
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_policy p ON p.polrelid = c.oid
        WHERE n.nspname = current_schema()
          AND c.relkind = 'r'
          AND c.relname NOT IN ('users', 'tenants', 'memberships')
          AND EXISTS (
              SELECT 1 FROM information_schema.columns ic
              WHERE ic.table_schema = n.nspname
                AND ic.table_name = c.relname
                AND ic.column_name = 'tenant_id'
          )
        GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity
        ORDER BY c.relname
    """))).mappings().all()
    assert rows, "No tenant-owned tables were discovered for RLS verification."
    failures = [
        dict(row) for row in rows
        if not row["rls_enabled"] or not row["force_rls"] or row["policy_count"] < 1
    ]
    assert not failures, f"Tenant tables without complete RLS protection: {failures}"


@pytest.mark.asyncio
async def test_rls_select_isolation(db_session: AsyncSession):
    await _assert_test_role_does_not_bypass_rls(db_session)
    tenant_a, user_a = await _create_identity(db_session, "A")
    tenant_b, user_b = await _create_identity(db_session, "B")

    with tenant_context(tenant_a.id, user_a.id):
        contact_a = await _create_contact(db_session, tenant_a, user_a, "TenantA")
    with tenant_context(tenant_b.id, user_b.id):
        contact_b = await _create_contact(db_session, tenant_b, user_b, "TenantB")

    with tenant_context(tenant_a.id, user_a.id):
        rows = (await db_session.execute(select(Contact))).scalars().all()
        ids = {row.id for row in rows}
        assert contact_a.id in ids
        assert contact_b.id not in ids

    with tenant_context(tenant_b.id, user_b.id):
        rows = (await db_session.execute(select(Contact))).scalars().all()
        ids = {row.id for row in rows}
        assert contact_b.id in ids
        assert contact_a.id not in ids


@pytest.mark.asyncio
async def test_rls_default_deny_without_context(db_session: AsyncSession):
    await _assert_test_role_does_not_bypass_rls(db_session)
    tenant, user = await _create_identity(db_session, "NoContext")
    with tenant_context(tenant.id, user.id):
        await _create_contact(db_session, tenant, user, "Owned")

    rows = (await db_session.execute(select(Contact))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_rls_insert_update_delete_enforcement(db_session: AsyncSession):
    await _assert_test_role_does_not_bypass_rls(db_session)
    tenant_a, user_a = await _create_identity(db_session, "WriteA")
    tenant_b, user_b = await _create_identity(db_session, "WriteB")

    with tenant_context(tenant_b.id, user_b.id):
        contact_b = await _create_contact(db_session, tenant_b, user_b, "ProtectedB")

    with tenant_context(tenant_a.id, user_a.id):
        wrong = Contact(
            tenant_id=tenant_b.id,
            first_name="Wrong",
            last_name="Tenant",
            email=f"wrong-{uuid4().hex[:10]}@example.test",
            created_by_id=user_a.id,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(wrong)
        with pytest.raises(DBAPIError) as exc_info:
            await db_session.commit()
        assert "row-level security" in str(exc_info.value).lower()
        await db_session.rollback()

        result = await db_session.execute(
            update(Contact).where(Contact.id == contact_b.id).values(last_name="BLOCKED")
        )
        await db_session.commit()
        assert result.rowcount == 0

        result = await db_session.execute(delete(Contact).where(Contact.id == contact_b.id))
        await db_session.commit()
        assert result.rowcount == 0


@pytest.mark.asyncio
async def test_rls_connection_context_switch_and_no_leak(db_session: AsyncSession):
    await _assert_test_role_does_not_bypass_rls(db_session)
    tenant_a, user_a = await _create_identity(db_session, "PoolA")
    tenant_b, user_b = await _create_identity(db_session, "PoolB")

    with tenant_context(tenant_a.id, user_a.id):
        contact_a = await _create_contact(db_session, tenant_a, user_a, "PoolA")
    with tenant_context(tenant_b.id, user_b.id):
        contact_b = await _create_contact(db_session, tenant_b, user_b, "PoolB")

    for tenant, user, own, other in [
        (tenant_a, user_a, contact_a, contact_b),
        (tenant_b, user_b, contact_b, contact_a),
        (tenant_a, user_a, contact_a, contact_b),
    ]:
        with tenant_context(tenant.id, user.id):
            rows = (await db_session.execute(select(Contact))).scalars().all()
            ids = {row.id for row in rows}
            assert own.id in ids
            assert other.id not in ids
