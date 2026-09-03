"""Test tenant isolation and multi-tenancy boundaries."""

import pytest
from httpx import AsyncClient

from app.models import Membership, RoleEnum, Tenant, User


@pytest.mark.asyncio
async def test_tenant_isolation(
    client: AsyncClient,
    db_session,
    test_user,
    test_tenant,
    auth_headers,
):
    """A tenant owner cannot fetch another tenant through a path parameter."""
    other_tenant = Tenant(
        name="Other Tenant",
        slug="other-tenant",
        is_active=True,
    )
    db_session.add(other_tenant)
    await db_session.flush()

    other_user = User(
        email="other@example.com",
        hashed_password=None,
        full_name="Other User",
        is_active=True,
        email_verified=True,
    )
    db_session.add(other_user)
    await db_session.flush()

    db_session.add(
        Membership(
            user_id=other_user.id,
            tenant_id=other_tenant.id,
            role=RoleEnum.OWNER,
            is_default=True,
        )
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/tenants/{other_tenant.id}",
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_x_tenant_header_must_match_token_tenant(
    client: AsyncClient,
    db_session,
    test_user,
    auth_headers,
):
    """A valid token cannot be replayed with another tenant's X-Tenant-ID."""
    other_tenant = Tenant(
        name="Header Isolation Tenant",
        slug="header-isolation-tenant",
        is_active=True,
    )
    db_session.add(other_tenant)
    await db_session.commit()

    mismatched_headers = {
        **auth_headers,
        "X-Tenant-ID": str(other_tenant.id),
    }
    response = await client.get("/api/v1/users", headers=mismatched_headers)

    assert response.status_code == 403
    assert "tenant" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_user_cannot_see_other_tenant_users(
    client: AsyncClient,
    db_session,
    test_user,
    test_tenant,
    auth_headers,
):
    """User listing is scoped to the active tenant."""
    other_tenant = Tenant(
        name="Other Tenant 2",
        slug="other-tenant-2",
        is_active=True,
    )
    db_session.add(other_tenant)
    await db_session.flush()

    other_user = User(
        email="other2@example.com",
        hashed_password=None,
        full_name="Other User 2",
        is_active=True,
        email_verified=True,
    )
    db_session.add(other_user)
    await db_session.flush()

    db_session.add(
        Membership(
            user_id=other_user.id,
            tenant_id=other_tenant.id,
            role=RoleEnum.SALES_EXECUTIVE,
            is_default=True,
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/users", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    user_emails = [user["email"] for user in data["items"]]
    assert "test@example.com" in user_emails
    assert "other2@example.com" not in user_emails


@pytest.mark.asyncio
async def test_tenant_switching(
    client: AsyncClient,
    db_session,
    test_user,
    test_tenant,
    auth_headers,
):
    """A user can switch to another tenant only when they have membership."""
    other_tenant = Tenant(
        name="Other Tenant 3",
        slug="other-tenant-3",
        is_active=True,
    )
    db_session.add(other_tenant)
    await db_session.flush()

    db_session.add(
        Membership(
            user_id=test_user.id,
            tenant_id=other_tenant.id,
            role=RoleEnum.ADMIN,
            is_default=False,
        )
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/auth/switch-tenant/{other_tenant.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data

    new_headers = {
        "Authorization": f"Bearer {data['access_token']}",
        "X-Tenant-ID": str(other_tenant.id),
    }
    response = await client.get("/api/v1/tenants/me", headers=new_headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(other_tenant.id)


@pytest.mark.asyncio
async def test_list_user_tenants(client: AsyncClient, auth_headers):
    """Authenticated users can list their own memberships."""
    response = await client.get("/api/v1/auth/tenants", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["slug"] == "test-tenant"
