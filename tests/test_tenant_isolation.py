"""
Test tenant isolation and multi-tenancy.
"""
import pytest
from httpx import AsyncClient
from uuid import uuid4

from app.models import Tenant, User, Membership, RoleEnum


@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient, db_session, test_user, test_tenant, auth_headers):
    """Test that users cannot access other tenants' data."""
    # Create another tenant
    other_tenant = Tenant(
        name="Other Tenant",
        slug="other-tenant",
        is_active=True,
    )
    db_session.add(other_tenant)
    await db_session.flush()
    
    # Create a user in the other tenant
    other_user = User(
        email="other@example.com",
        hashed_password="$2b$12$testhashedpassword",
        full_name="Other User",
        is_active=True,
        email_verified=True,
    )
    db_session.add(other_user)
    await db_session.flush()
    
    other_membership = Membership(
        user_id=other_user.id,
        tenant_id=other_tenant.id,
        role=RoleEnum.OWNER,
        is_default=True,
    )
    db_session.add(other_membership)
    await db_session.commit()
    
    # Try to access other tenant's data with current user's token
    # This should fail because the token is for test_tenant, not other_tenant
    response = await client.get(
        f"/api/v1/tenants/{other_tenant.id}",
        headers=auth_headers,
    )
    # Should be forbidden or not found since user is not a member
    assert response.status_code in [403, 404]


@pytest.mark.asyncio
async def test_user_cannot_see_other_tenant_users(client: AsyncClient, db_session, test_user, test_tenant, auth_headers):
    """Test that users cannot see users from other tenants."""
    # Create another tenant with a user
    other_tenant = Tenant(
        name="Other Tenant 2",
        slug="other-tenant-2",
        is_active=True,
    )
    db_session.add(other_tenant)
    await db_session.flush()
    
    other_user = User(
        email="other2@example.com",
        hashed_password="$2b$12$testhashedpassword",
        full_name="Other User 2",
        is_active=True,
        email_verified=True,
    )
    db_session.add(other_user)
    await db_session.flush()
    
    other_membership = Membership(
        user_id=other_user.id,
        tenant_id=other_tenant.id,
        role=RoleEnum.SALES_EXECUTIVE,
        is_default=True,
    )
    db_session.add(other_membership)
    await db_session.commit()
    
    # List users - should only see users from test_tenant
    response = await client.get("/api/v1/users", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    # Should only see test_user (and maybe themselves)
    user_emails = [u["email"] for u in data["items"]]
    assert "test@example.com" in user_emails
    assert "other2@example.com" not in user_emails


@pytest.mark.asyncio
async def test_tenant_switching(client: AsyncClient, db_session, test_user, test_tenant, auth_headers):
    """Test switching between tenants."""
    # Create another tenant and add test_user as member
    other_tenant = Tenant(
        name="Other Tenant 3",
        slug="other-tenant-3",
        is_active=True,
    )
    db_session.add(other_tenant)
    await db_session.flush()
    
    membership = Membership(
        user_id=test_user.id,
        tenant_id=other_tenant.id,
        role=RoleEnum.ADMIN,
        is_default=False,
    )
    db_session.add(membership)
    await db_session.commit()
    
    # Switch to other tenant
    response = await client.post(
        f"/api/v1/auth/switch-tenant/{other_tenant.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    
    # Use new token to access other tenant
    new_headers = {"Authorization": f"Bearer {data['access_token']}"}
    response = await client.get("/api/v1/tenants/me", headers=new_headers)
    assert response.status_code == 200
    tenant_data = response.json()
    assert tenant_data["id"] == str(other_tenant.id)


@pytest.mark.asyncio
async def test_list_user_tenants(client: AsyncClient, auth_headers):
    """Test listing all tenants for current user."""
    response = await client.get("/api/v1/auth/tenants", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["slug"] == "test-tenant"