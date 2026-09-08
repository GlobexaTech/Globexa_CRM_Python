"""
Users API routes for Globexa CRM.
User management within a tenant.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import get_current_active_user, require_manager_or_above, require_admin, get_tenant_id
from app.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserWithMemberships,
    MembershipCreate,
    MembershipUpdate,
    MembershipResponse,
    PaginationParams,
    PaginatedResponse,
)
from app.models import User, Membership, RoleEnum, Tenant
from app.core.security import hash_password, generate_secure_token
from app.services.auth.service import AuthService
from app.core.rbac import may_assign_role

def check_assignment(current_user, role):
    try:
        target = RoleEnum(role)
    except ValueError:
        raise HTTPException(422, "Unknown role") from None
    if not may_assign_role(current_user[1].role, target):
        raise HTTPException(403, "Role assignment forbidden")
    return target


router = APIRouter(prefix="/users", tags=["Users"])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    current_user: tuple = Depends(require_manager_or_above),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a new user in the current tenant."""
    check_assignment(current_user, data.role)
    # Check if email already exists globally
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create user
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        avatar_url=data.avatar_url,
        phone=data.phone,
        timezone=data.timezone,
        locale=data.locale,
        is_active=True,
        is_superuser=False,
        email_verified=False,
    )
    db.add(user)
    await db.flush()

    # Create membership
    membership = Membership(
        user_id=user.id,
        tenant_id=tenant_id,
        role=RoleEnum(data.role) if hasattr(data, 'role') else RoleEnum.SALES_EXECUTIVE,
        is_default=data.is_default if hasattr(data, 'is_default') else False,
    )
    db.add(membership)

    await db.commit()
    await db.refresh(user)
    return user


@router.get("", response_model=PaginatedResponse)
async def list_users(
    params: PaginationParams = Depends(),
    role: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: tuple = Depends(require_manager_or_above),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List users in the current tenant."""
    query = (
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == tenant_id)
        .order_by(User.created_at.desc())
    )

    if role:
        query = query.where(Membership.role == RoleEnum(role))
    if is_active is not None:
        query = query.where(User.is_active == is_active)

    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    users = result.scalars().all()

    return PaginatedResponse.create(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        params=params,
    )


@router.get("/me", response_model=UserWithMemberships)
async def get_my_profile(
    current_user: tuple = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's full profile with all memberships."""
    user, _ = current_user

    # Reload with memberships
    result = await db.execute(
        select(User)
        .where(User.id == user.id)
        .options(selectinload(User.memberships).selectinload(Membership.tenant))
    )
    user = result.scalar_one()
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_user: tuple = Depends(require_manager_or_above),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get a user in the current tenant."""
    result = await db.execute(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(User.id == user_id, Membership.tenant_id == tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found in this tenant")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    current_user: tuple = Depends(require_manager_or_above),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a user in the current tenant."""
    result = await db.execute(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(User.id == user_id, Membership.tenant_id == tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found in this tenant")

    # Prevent self-demotion
    current_user_obj, current_membership = current_user
    if user.id == current_user_obj.id:
        # Don't allow deactivating yourself
        pass

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    current_user: tuple = Depends(require_manager_or_above),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Remove a user from the current tenant (soft delete - removes membership)."""
    current_user_obj, current_membership = current_user

    if user_id == current_user_obj.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="User not found in this tenant")

    check_assignment(current_user, membership.role)
    # Don't allow removing the last owner
    if membership.role == RoleEnum.OWNER:
        owner_count = await db.scalar(
            select(func.count()).select_from(Membership).where(
                Membership.tenant_id == tenant_id,
                Membership.role == RoleEnum.OWNER,
            )
        )
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last owner")

    await db.delete(membership)
    await db.commit()


# Membership management
@router.post("/{user_id}/memberships", response_model=MembershipResponse, status_code=status.HTTP_201_CREATED)
async def add_user_to_tenant(
    user_id: UUID,
    data: MembershipCreate,
    current_user: tuple = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Add an existing user to the current tenant."""
    check_assignment(current_user, data.role)
    # Verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if already a member
    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already a member of this tenant")

    membership = Membership(
        user_id=user_id,
        tenant_id=tenant_id,
        role=RoleEnum(data.role),
        is_default=data.is_default,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return membership


@router.patch("/{user_id}/memberships", response_model=MembershipResponse)
async def update_membership(
    user_id: UUID,
    data: MembershipUpdate,
    current_user: tuple = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a user's membership in the current tenant."""
    current_user_obj, current_membership = current_user

    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    if data.role:
        check_assignment(current_user, data.role)
        if user_id == current_user_obj.id:
            raise HTTPException(403, "Cannot change your own role")
    # Prevent self-demotion
    if user_id == current_user_obj.id:
        if data.role and RoleEnum(data.role) != RoleEnum.OWNER:
            raise HTTPException(status_code=400, detail="Cannot change your own role from owner")
        if data.is_default is False:
            raise HTTPException(status_code=400, detail="Cannot unset default tenant for yourself")

    check_assignment(current_user, membership.role)
    # Prevent removing last owner
    if membership.role == RoleEnum.OWNER and data.role and RoleEnum(data.role) != RoleEnum.OWNER:
        owner_count = await db.scalar(
            select(func.count()).select_from(Membership).where(
                Membership.tenant_id == tenant_id,
                Membership.role == RoleEnum.OWNER,
            )
        )
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last owner")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "role":
            value = RoleEnum(value)
        setattr(membership, field, value)

    await db.commit()
    await db.refresh(membership)
    return membership


@router.delete("/{user_id}/memberships", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_from_tenant(
    user_id: UUID,
    current_user: tuple = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Remove a user from the current tenant."""
    current_user_obj, _ = current_user

    if user_id == current_user_obj.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    check_assignment(current_user, membership.role)
    # Prevent removing last owner
    if membership.role == RoleEnum.OWNER:
        owner_count = await db.scalar(
            select(func.count()).select_from(Membership).where(
                Membership.tenant_id == tenant_id,
                Membership.role == RoleEnum.OWNER,
            )
        )
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last owner")

    await db.delete(membership)
    await db.commit()