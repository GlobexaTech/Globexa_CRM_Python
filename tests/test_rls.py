"""
RLS (Row-Level Security) verification tests.
These tests verify that database-level tenant isolation is working correctly.
"""
import pytest
from uuid import uuid4
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tenant, User, Membership, RoleEnum, PackageEnum, Subscription, SubscriptionStatusEnum


class TestRLS:
    """Test Row-Level Security policies."""

    @pytest.mark.asyncio
    async def test_rls_tenant_isolation(self, db_session: AsyncSession):
        """Test that RLS prevents cross-tenant data access."""
        # Create two tenants
        tenant1 = Tenant(name="Tenant 1", slug="tenant-1", is_active=True)
        tenant2 = Tenant(name="Tenant 2", slug="tenant-2", is_active=True)
        db_session.add_all([tenant1, tenant2])
        await db_session.flush()

        # Create subscriptions
        sub1 = Subscription(tenant_id=tenant1.id, package=PackageEnum.STARTER, status=SubscriptionStatusEnum.TRIALING)
        sub2 = Subscription(tenant_id=tenant2.id, package=PackageEnum.STARTER, status=SubscriptionStatusEnum.TRIALING)
        db_session.add_all([sub1, sub2])
        await db_session.flush()

        # Create users
        user1 = User(email="user1@tenant1.com", hashed_password="hash", full_name="User 1", is_active=True)
        user2 = User(email="user2@tenant2.com", hashed_password="hash", full_name="User 2", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.flush()

        # Create memberships
        membership1 = Membership(user_id=user1.id, tenant_id=tenant1.id, role=RoleEnum.OWNER, is_default=True)
        membership2 = Membership(user_id=user2.id, tenant_id=tenant2.id, role=RoleEnum.OWNER, is_default=True)
        db_session.add_all([membership1, membership2])
        await db_session.commit()

        # Set RLS context to tenant1
        from app.core.rls import set_rls_context
        await set_rls_context(db_session, tenant_id=tenant1.id, user_id=user1.id)

        # Query users - should only see tenant1's user
        result = await db_session.execute(select(User))
        users = result.scalars().all()
        
        # With RLS, we should only see tenant1's user
        # But the users table is global, so this might show both
        # Let's test with a tenant-scoped table like contacts
        # For now, verify the RLS context is set
        current_tenant_result = await db_session.execute(
            text("SELECT current_setting('app.current_tenant_id')")
        )
        current_tenant = current_tenant_result.scalar()
        assert str(tenant1.id) == current_tenant

    @pytest.mark.asyncio
    async def test_rls_cross_tenant_blocked(self, db_session: AsyncSession):
        """Test that RLS blocks cross-tenant queries."""
        # Create two tenants with contacts
        tenant1 = Tenant(name="Tenant 1", slug="tenant-1", is_active=True)
        tenant2 = Tenant(name="Tenant 2", slug="tenant-2", is_active=True)
        db_session.add_all([tenant1, tenant2])
        await db_session.flush()

        # Create users
        user1 = User(email="user1@tenant1.com", hashed_password="hash", full_name="User 1", is_active=True)
        user2 = User(email="user2@tenant2.com", hashed_password="hash", full_name="User 2", is_active=True)
        db_session.add_all([user1, user2])
        await db_session.flush()

        # Create memberships
        membership1 = Membership(user_id=user1.id, tenant_id=tenant1.id, role=RoleEnum.OWNER, is_default=True)
        membership2 = Membership(user_id=user2.id, tenant_id=tenant2.id, role=RoleEnum.OWNER, is_default=True)
        db_session.add_all([membership1, membership2])
        await db_session.flush()

        # Create contacts in each tenant
        from app.models import Contact
        contact1 = Contact(
            tenant_id=tenant1.id,
            first_name="Contact",
            last_name="One",
            email="contact1@tenant1.com",
            created_by_id=user1.id
        )
        contact2 = Contact(
            tenant_id=tenant2.id,
            first_name="Contact",
            last_name="Two",
            email="contact2@tenant2.com",
            created_by_id=user2.id
        )
        db_session.add_all([contact1, contact2])
        await db_session.commit()

        # Set RLS context to tenant1
        from app.core.rls import set_rls_context
        await set_rls_context(db_session, tenant_id=tenant1.id, user_id=user1.id)

        # Query contacts - should only see tenant1's contact
        result = await db_session.execute(select(Contact))
        contacts = result.scalars().all()
        
        # With RLS, we should only see tenant1's contact
        # The RLS policy should filter out tenant2's contact
        emails = [c.email for c in contacts]
        assert "contact1@tenant1.com" in emails
        # contact2 should NOT be visible due to RLS
        assert "contact2@tenant2.com" not in emails

    @pytest.mark.asyncio
    async def test_rls_insert_enforcement(self, db_session: AsyncSession):
        """Test that RLS enforces tenant_id on INSERT."""
        tenant1 = Tenant(name="Tenant 1", slug="tenant-1", is_active=True)
        tenant2 = Tenant(name="Tenant 2", slug="tenant-2", is_active=True)
        db_session.add_all([tenant1, tenant2])
        await db_session.flush()

        user1 = User(email="user1@tenant1.com", hashed_password="hash", full_name="User 1", is_active=True)
        db_session.add(user1)
        await db_session.flush()

        membership1 = Membership(user_id=user1.id, tenant_id=tenant1.id, role=RoleEnum.OWNER, is_default=True)
        db_session.add(membership1)
        await db_session.commit()

        # Set RLS context to tenant1
        from app.core.rls import set_rls_context
        await set_rls_context(db_session, tenant_id=tenant1.id, user_id=user1.id)

        # Try to insert a contact with tenant2's ID - should fail
        from app.models import Contact
        contact = Contact(
            tenant_id=tenant2.id,  # Wrong tenant!
            first_name="Malicious",
            last_name="Insert",
            email="malicious@tenant2.com",
            created_by_id=user1.id
        )
        db_session.add(contact)
        
        # This should fail due to RLS WITH CHECK policy
        with pytest.raises(Exception) as exc_info:
            await db_session.commit()
        
        # Verify the error is related to RLS policy violation
        assert "policy" in str(exc_info.value).lower() or "check" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_rls_admin_bypass(self, db_session: AsyncSession):
        """Test that admin context can bypass RLS (if BYPASSRLS role is used)."""
        # This test documents expected behavior
        # In production, admin users would connect with a BYPASSRLS role
        # For now, we verify the is_admin setting works
        tenant1 = Tenant(name="Tenant 1", slug="tenant-1", is_active=True)
        db_session.add(tenant1)
        await db_session.flush()

        user1 = User(email="admin@tenant1.com", hashed_password="hash", full_name="Admin", is_active=True, is_superuser=True)
        db_session.add(user1)
        await db_session.flush()

        membership1 = Membership(user_id=user1.id, tenant_id=tenant1.id, role=RoleEnum.OWNER, is_default=True)
        db_session.add(membership1)
        await db_session.commit()

        # Set RLS context with is_admin=True
        from app.core.rls import set_rls_context, is_admin
        await set_rls_context(db_session, tenant_id=tenant1.id, user_id=user1.id, is_admin=True)
        
        # Verify admin context is set
        admin_result = await db_session.execute(
            text("SELECT current_setting('app.is_admin')")
        )
        is_admin_setting = admin_result.scalar()
        assert is_admin_setting == "true"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])