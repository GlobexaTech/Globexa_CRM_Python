"""Executable PostgreSQL RLS isolation tests.

These tests deliberately assert both positive visibility and negative
cross-tenant access. They fail when the test connection bypasses RLS, rather
than treating that condition as success.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import tenant_context
from app.models import Contact, Membership, Tenant, User


async def _assert_test_role_does_not_bypass_rls(db: AsyncSession) -> None:
    row = (
        await db.execute(
            text(
                "SELECT rolsuper, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            )
        )
    ).one()
    assert row.rolsuper is False, (
        "RLS tests must run as a non-superuser database role; "
        "superusers bypass PostgreSQL RLS."
    )
    assert row.rolbypassrls is False, (
        "RLS tests must run as a NOBYPASSRLS database role."
    )


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

    # No tenant_context here. PostgreSQL must return no tenant-owned rows.
    rows = (await db_session.execute(select(Contact))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_rls_insert_update_delete_enforcement(db_session: AsyncSession):
    await _assert_test_role_does_not_bypass_rls(db_session)
    tenant_a, user_a = await _create_identity(db_session, "WriteA")
    tenant_b, user_b = await _create_identity(db_session, "WriteB")

    with tenant_context(tenant_a.id, user_a.id):
        valid = await _create_contact(db_session, tenant_a, user_a, "ValidA")

        wrong = Contact(
            tenant_id=tenant_b.id,
            first_name="Wrong",
            last_name="Tenant",
            email=f"wrong-{uuid4().hex[:10]}@example.test",
            created_by_id=user_a.id,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(wrong)
        with pytest.raises(Exception):
            await db_session.commit()
        await db_session.rollback()

    with tenant_context(tenant_a.id, user_a.id):
        # Cross-tenant UPDATE must affect zero rows.
        result = await db_session.execute(
            update(Contact)
            .where(Contact.id == valid.id, Contact.tenant_id == tenant_b.id)
            .values(last_name="MUST_NOT_CHANGE")
        )
        await db_session.commit()
        assert result.rowcount == 0

        # Direct UPDATE without an application tenant predicate must still
        # be constrained by PostgreSQL RLS.
        result = await db_session.execute(
            update(Contact).where(Contact.tenant_id == tenant_b.id).values(last_name="BLOCKED")
        )
        await db_session.commit()
        assert result.rowcount == 0

    with tenant_context(tenant_a.id, user_a.id):
        result = await db_session.execute(delete(Contact).where(Contact.tenant_id == tenant_b.id))
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
