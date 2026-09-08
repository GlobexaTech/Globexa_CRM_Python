"""
Tenant API routes for Globexa CRM.
Tenant management, subscription, feature entitlements.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import get_current_active_user, require_admin, get_tenant_id
from app.schemas import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    TenantWithSubscription,
    SubscriptionCreate,
    SubscriptionUpdate,
    SubscriptionResponse,
    FeatureEntitlementCreate,
    FeatureEntitlementUpdate,
    FeatureEntitlementResponse,
    PaginationParams,
    PaginatedResponse,
)
from app.models import Tenant, Subscription, FeatureEntitlement, PackageEnum, SubscriptionStatusEnum, Membership, RoleEnum

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    data: TenantCreate,
    current_user: tuple = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new tenant (admin only)."""
    # Check slug uniqueness
    result = await db.execute(select(Tenant).where(Tenant.slug == data.slug))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Slug already taken")

    # Check domain uniqueness if provided
    if data.domain:
        result = await db.execute(select(Tenant).where(Tenant.domain == data.domain))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Domain already taken")

    tenant = Tenant(**data.model_dump())
    from uuid import uuid4
    from app.core.tenant_context import bind_context
    tenant.id = uuid4()
    await bind_context(db, tenant.id, current_user[0].id)
    db.add(tenant)
    await db.flush()

    # Create default subscription
    subscription = Subscription(
        tenant_id=tenant.id,
        package=PackageEnum.STARTER,
        status=SubscriptionStatusEnum.TRIALING,
    )
    db.add(subscription)

    # Create default entitlements
    from app.services.auth.service import AuthService
    auth_service = AuthService(db)
    await auth_service._create_default_entitlements(tenant.id, PackageEnum.STARTER)

    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.get("", response_model=PaginatedResponse)
async def list_tenants(
    params: PaginationParams = Depends(),
    current_user: tuple = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all tenants (admin only)."""
    query = select(Tenant).where(Tenant.id == current_user[1].tenant_id).order_by(Tenant.created_at.desc())
    total_query = select(func.count()).select_from(query.subquery())

    total = await db.scalar(total_query)
    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    tenants = result.scalars().all()

    return PaginatedResponse.create(
        items=[TenantResponse.model_validate(t) for t in tenants],
        total=total,
        params=params,
    )


@router.get("/me", response_model=TenantWithSubscription)
async def get_my_tenant(
    tenant_id: UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Get current tenant with subscription and entitlements."""
    result = await db.execute(
        select(Tenant)
        .where(Tenant.id == tenant_id)
        .options(
            selectinload(Tenant.subscription),
            selectinload(Tenant.feature_entitlements),
        )
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return tenant


@router.get("/{tenant_id}", response_model=TenantWithSubscription)
async def get_tenant(
    tenant_id: UUID,
    current_user: tuple = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant by ID (admin only)."""
    result = await db.execute(
        select(Tenant)
        .where(Tenant.id == tenant_id)
        .options(
            selectinload(Tenant.subscription),
            selectinload(Tenant.feature_entitlements),
        )
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return tenant


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    data: TenantUpdate,
    current_user: tuple = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update tenant (admin only)."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = data.model_dump(exclude_unset=True)

    # Check uniqueness
    if "slug" in update_data:
        existing = await db.execute(
            select(Tenant).where(Tenant.slug == update_data["slug"], Tenant.id != tenant_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Slug already taken")

    if "domain" in update_data and update_data["domain"]:
        existing = await db.execute(
            select(Tenant).where(Tenant.domain == update_data["domain"], Tenant.id != tenant_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Domain already taken")

    for field, value in update_data.items():
        setattr(tenant, field, value)

    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: UUID,
    current_user: tuple = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete tenant (admin only)."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await db.delete(tenant)
    await db.commit()


# Subscription endpoints

@router.get("/{tenant_id}/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    tenant_id: UUID,
    current_user: tuple = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant subscription."""
    result = await db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
    subscription = result.scalar_one_or_none()
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return subscription



@router.get("/{tenant_id}/entitlements", response_model=List[FeatureEntitlementResponse])
async def list_entitlements(
    tenant_id: UUID,
    current_user: tuple = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all feature entitlements for a tenant."""
    result = await db.execute(
        select(FeatureEntitlement).where(FeatureEntitlement.tenant_id == tenant_id)
    )
    return result.scalars().all()




@router.delete("/{tenant_id}/entitlements/{feature_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entitlement(
    tenant_id: UUID,
    feature_key: str,
    current_user: tuple = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a feature entitlement."""
    result = await db.execute(
        select(FeatureEntitlement).where(
            FeatureEntitlement.tenant_id == tenant_id,
            FeatureEntitlement.feature_key == feature_key,
        )
    )
    entitlement = result.scalar_one_or_none()
    if not entitlement:
        raise HTTPException(status_code=404, detail="Entitlement not found")

    await db.delete(entitlement)
    await db.commit()