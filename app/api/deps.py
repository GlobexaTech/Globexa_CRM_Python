"""
FastAPI dependencies for authentication and authorization.
"""
from typing import Optional, List, Set
from uuid import UUID
from fastapi import Depends, HTTPException, status, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import decode_token
from app.models import User, Membership, RoleEnum, FeatureEntitlement
from app.services.auth.service import AuthService

from app.core.rbac import ROLE_HIERARCHY, ROLE_PERMISSIONS, ALL_PERMISSIONS, Permission, get_role_permissions


async def get_current_user_optional(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[tuple[User, Membership]]:
    """Get current user from token (optional - returns None if no valid token)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")

    if not user_id or not tenant_id:
        return None

    auth_service = AuthService(db)
    result = await auth_service.get_current_user(token)
    return result


async def get_current_user(
    request: Request,
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, Membership]:
    """Get current user from token (required - raises 401 if invalid)."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not authorization or not authorization.startswith("Bearer "):
        raise credentials_exception

    token = authorization.replace("Bearer ", "")
    auth_service = AuthService(db)
    result = await auth_service.get_current_user(token)

    if not result:
        raise credentials_exception

    user, membership = result
    # Set user's tenant_id in request state for X-Tenant-ID validation
    request.state.user_tenant_id = membership.tenant_id

    return result


async def get_current_active_user(
    current_user: tuple[User, Membership] = Depends(get_current_user),
) -> tuple[User, Membership]:
    """Ensure user is active."""
    user, membership = current_user
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return current_user


def require_permission(permission: Permission):
    """Dependency factory to require a specific permission."""
    async def permission_checker(
        current_user: tuple[User, Membership] = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> tuple[User, Membership]:
        user, membership = current_user
        role_perms = get_role_permissions(membership.role)

        # Check feature entitlements for feature permissions
        if permission.startswith("feature:"):
            feature_key = permission.replace("feature:", "")
            result = await db.execute(
                select(FeatureEntitlement).where(
                    FeatureEntitlement.tenant_id == membership.tenant_id,
                    FeatureEntitlement.feature_key == feature_key,
                    FeatureEntitlement.enabled == True,
                )
            )
            entitlement = result.scalar_one_or_none()
            if not entitlement:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Feature '{feature_key}' not enabled for this tenant",
                )

        if permission not in role_perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
            )

        return current_user

    return permission_checker


def require_role(*roles: RoleEnum):
    """Dependency factory to require one of the specified roles."""
    async def role_checker(
        current_user: tuple[User, Membership] = Depends(get_current_active_user),
    ) -> tuple[User, Membership]:
        user, membership = current_user
        if membership.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {membership.role.value} not authorized. Required: {[r.value for r in roles]}",
            )
        return current_user

    return role_checker


def require_min_role(min_role: RoleEnum):
    """Dependency factory to require at least a minimum role level."""
    async def role_checker(
        current_user: tuple[User, Membership] = Depends(get_current_active_user),
    ) -> tuple[User, Membership]:
        user, membership = current_user
        user_level = ROLE_HIERARCHY.get(membership.role, 0)
        required_level = ROLE_HIERARCHY.get(min_role, 0)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Minimum role {min_role.value} required",
            )
        return current_user

    return role_checker


# Common permission dependencies
require_leads_read = require_permission(Permission.LEADS_READ)
require_leads_write = require_permission(Permission.LEADS_WRITE)
require_leads_assign = require_permission(Permission.LEADS_ASSIGN)
require_contacts_read = require_permission(Permission.CONTACTS_READ)
require_contacts_write = require_permission(Permission.CONTACTS_WRITE)
require_deals_read = require_permission(Permission.DEALS_READ)
require_deals_write = require_permission(Permission.DEALS_WRITE)
require_campaigns_read = require_permission(Permission.CAMPAIGNS_READ)
require_campaigns_write = require_permission(Permission.CAMPAIGNS_WRITE)
require_campaigns_send = require_permission(Permission.CAMPAIGNS_SEND)
require_campaigns_analytics = require_permission(Permission.CAMPAIGNS_ANALYTICS)
require_campaigns_audience = require_permission(Permission.CAMPAIGNS_AUDIENCE)
require_campaigns_template = require_permission(Permission.CAMPAIGNS_TEMPLATE)
require_campaigns_sequence = require_permission(Permission.CAMPAIGNS_SEQUENCE)
require_campaigns_trigger = require_permission(Permission.CAMPAIGNS_TRIGGER)
require_integrations_read = require_permission(Permission.INTEGRATIONS_READ)
require_integrations_write = require_permission(Permission.INTEGRATIONS_WRITE)
require_integrations_webhooks = require_permission(Permission.INTEGRATIONS_WEBHOOKS)
require_ai_scoring = require_permission(Permission.AI_SCORE_LEADS)
require_ai_chat = require_permission(Permission.AI_CHAT)
require_admin = require_role(RoleEnum.ADMIN, RoleEnum.OWNER)
require_manager_or_above = require_min_role(RoleEnum.SALES_MANAGER)

# Re-export tenant utilities from middleware
from app.middleware.tenant import get_tenant_id, get_tenant