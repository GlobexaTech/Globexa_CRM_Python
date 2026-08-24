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

# Role hierarchy (higher = more permissions)
ROLE_HIERARCHY = {
    RoleEnum.VIEWER: 0,
    RoleEnum.SALES_EXECUTIVE: 10,
    RoleEnum.MARKETING: 20,
    RoleEnum.SALES_MANAGER: 30,
    RoleEnum.ADMIN: 40,
    RoleEnum.OWNER: 50,
}

# Permission definitions
ALL_PERMISSIONS = [
    # CRM permissions
    "leads:read",
    "leads:write",
    "leads:delete",
    "leads:assign",
    "leads:export",
    "contacts:read",
    "contacts:write",
    "contacts:delete",
    "contacts:import",
    "companies:read",
    "companies:write",
    "companies:delete",
    "deals:read",
    "deals:write",
    "deals:delete",
    "deals:pipeline_manage",
    "tasks:read",
    "tasks:write",
    "tasks:delete",
    # Campaign permissions
    "campaigns:read",
    "campaigns:write",
    "campaigns:delete",
    "campaigns:send",
    "campaigns:analytics",
    "campaigns:audience",
    "campaigns:template",
    "campaigns:sequence",
    "campaigns:trigger",
    # AI permissions (per blueprint)
    "ai:read_leads",
    "ai:score_leads",
    "ai:assign_leads",
    "ai:draft_email",
    "ai:send_email",
    "ai:schedule_email",
    "ai:read_replies",
    "ai:respond_email",
    "ai:create_proposal",
    "ai:change_stage",
    "ai:chat",
    # Integration permissions
    "integrations:read",
    "integrations:write",
    "integrations:webhooks",
    # Admin permissions
    "users:read",
    "users:write",
    "users:delete",
    "tenant:settings",
    "billing:read",
    "billing:write",
    "audit:logs",
    # Feature entitlements
    "feature:ai_scoring",
    "feature:ai_miner",
    "feature:campaigns",
    "feature:whatsapp",
    "feature:api",
]

class Permission:
    # CRM permissions
    LEADS_READ = "leads:read"
    LEADS_WRITE = "leads:write"
    LEADS_DELETE = "leads:delete"
    LEADS_ASSIGN = "leads:assign"
    LEADS_EXPORT = "leads:export"

    CONTACTS_READ = "contacts:read"
    CONTACTS_WRITE = "contacts:write"
    CONTACTS_DELETE = "contacts:delete"
    CONTACTS_IMPORT = "contacts:import"

    COMPANIES_READ = "companies:read"
    COMPANIES_WRITE = "companies:write"
    COMPANIES_DELETE = "companies:delete"

    DEALS_READ = "deals:read"
    DEALS_WRITE = "deals:write"
    DEALS_DELETE = "deals:delete"
    DEALS_PIPELINE_MANAGE = "deals:pipeline_manage"

    TASKS_READ = "tasks:read"
    TASKS_WRITE = "tasks:write"
    TASKS_DELETE = "tasks:delete"

    # Campaign permissions
    CAMPAIGNS_READ = "campaigns:read"
    CAMPAIGNS_WRITE = "campaigns:write"
    CAMPAIGNS_DELETE = "campaigns:delete"
    CAMPAIGNS_SEND = "campaigns:send"
    CAMPAIGNS_ANALYTICS = "campaigns:analytics"
    CAMPAIGNS_AUDIENCE = "campaigns:audience"
    CAMPAIGNS_TEMPLATE = "campaigns:template"
    CAMPAIGNS_SEQUENCE = "campaigns:sequence"
    CAMPAIGNS_TRIGGER = "campaigns:trigger"

    # AI permissions (per blueprint)
    AI_READ_LEADS = "ai:read_leads"
    AI_SCORE_LEADS = "ai:score_leads"
    AI_ASSIGN_LEADS = "ai:assign_leads"
    AI_DRAFT_EMAIL = "ai:draft_email"
    AI_SEND_EMAIL = "ai:send_email"
    AI_SCHEDULE_EMAIL = "ai:schedule_email"
    AI_READ_REPLIES = "ai:read_replies"
    AI_RESPOND_EMAIL = "ai:respond_email"
    AI_CREATE_PROPOSAL = "ai:create_proposal"
    AI_CHANGE_STAGE = "ai:change_stage"
    AI_CHAT = "ai:chat"

    # Integration permissions
    INTEGRATIONS_READ = "integrations:read"
    INTEGRATIONS_WRITE = "integrations:write"
    INTEGRATIONS_WEBHOOKS = "integrations:webhooks"

    # Admin permissions
    USERS_READ = "users:read"
    USERS_WRITE = "users:write"
    USERS_DELETE = "users:delete"
    TENANT_SETTINGS = "tenant:settings"
    BILLING_READ = "billing:read"
    BILLING_WRITE = "billing:write"
    AUDIT_LOGS = "audit:logs"

    # Feature entitlements
    FEATURE_AI_SCORING = "feature:ai_scoring"
    FEATURE_AI_MINER = "feature:ai_miner"
    FEATURE_CAMPAIGNS = "feature:campaigns"
    FEATURE_WHATSAPP = "feature:whatsapp"
    FEATURE_API = "feature:api"


# Role -> Permissions mapping
ROLE_PERMISSIONS: dict[RoleEnum, Set[Permission]] = {
    RoleEnum.VIEWER: {
        Permission.LEADS_READ,
        Permission.CONTACTS_READ,
        Permission.COMPANIES_READ,
        Permission.DEALS_READ,
        Permission.TASKS_READ,
        Permission.CAMPAIGNS_READ,
    },
    RoleEnum.SALES_EXECUTIVE: {
        Permission.LEADS_READ,
        Permission.LEADS_WRITE,
        Permission.LEADS_ASSIGN,  # Can assign their own leads
        Permission.CONTACTS_READ,
        Permission.CONTACTS_WRITE,
        Permission.COMPANIES_READ,
        Permission.COMPANIES_WRITE,
        Permission.DEALS_READ,
        Permission.DEALS_WRITE,
        Permission.TASKS_READ,
        Permission.TASKS_WRITE,
        Permission.CAMPAIGNS_READ,
        Permission.AI_READ_LEADS,
        Permission.AI_SCORE_LEADS,
        Permission.AI_ASSIGN_LEADS,
        Permission.AI_DRAFT_EMAIL,
        Permission.AI_SEND_EMAIL,
        Permission.AI_READ_REPLIES,
        Permission.AI_RESPOND_EMAIL,
        Permission.AI_CREATE_PROPOSAL,
        Permission.AI_CHANGE_STAGE,
        Permission.AI_CHAT,
    },
    RoleEnum.MARKETING: {
        Permission.LEADS_READ,
        Permission.LEADS_WRITE,
        Permission.LEADS_EXPORT,
        Permission.CONTACTS_READ,
        Permission.CONTACTS_WRITE,
        Permission.CONTACTS_IMPORT,
        Permission.COMPANIES_READ,
        Permission.COMPANIES_WRITE,
        Permission.DEALS_READ,
        Permission.CAMPAIGNS_READ,
        Permission.CAMPAIGNS_WRITE,
        Permission.CAMPAIGNS_SEND,
        Permission.CAMPAIGNS_ANALYTICS,
        Permission.CAMPAIGNS_AUDIENCE,
        Permission.CAMPAIGNS_TEMPLATE,
        Permission.CAMPAIGNS_SEQUENCE,
        Permission.CAMPAIGNS_TRIGGER,
        Permission.AI_READ_LEADS,
        Permission.AI_DRAFT_EMAIL,
        Permission.AI_CHAT,
        Permission.FEATURE_CAMPAIGNS,
        Permission.INTEGRATIONS_READ,
        Permission.INTEGRATIONS_WRITE,
        Permission.INTEGRATIONS_WEBHOOKS,
    },
    RoleEnum.SALES_MANAGER: {
        Permission.LEADS_READ,
        Permission.LEADS_WRITE,
        Permission.LEADS_DELETE,
        Permission.LEADS_ASSIGN,
        Permission.LEADS_EXPORT,
        Permission.CONTACTS_READ,
        Permission.CONTACTS_WRITE,
        Permission.CONTACTS_DELETE,
        Permission.CONTACTS_IMPORT,
        Permission.COMPANIES_READ,
        Permission.COMPANIES_WRITE,
        Permission.COMPANIES_DELETE,
        Permission.DEALS_READ,
        Permission.DEALS_WRITE,
        Permission.DEALS_DELETE,
        Permission.DEALS_PIPELINE_MANAGE,
        Permission.TASKS_READ,
        Permission.TASKS_WRITE,
        Permission.TASKS_DELETE,
        Permission.CAMPAIGNS_READ,
        Permission.CAMPAIGNS_WRITE,
        Permission.CAMPAIGNS_SEND,
        Permission.CAMPAIGNS_ANALYTICS,
        Permission.CAMPAIGNS_AUDIENCE,
        Permission.CAMPAIGNS_TEMPLATE,
        Permission.CAMPAIGNS_SEQUENCE,
        Permission.CAMPAIGNS_TRIGGER,
        Permission.AI_READ_LEADS,
        Permission.AI_SCORE_LEADS,
        Permission.AI_ASSIGN_LEADS,
        Permission.AI_DRAFT_EMAIL,
        Permission.AI_SEND_EMAIL,
        Permission.AI_READ_REPLIES,
        Permission.AI_RESPOND_EMAIL,
        Permission.AI_CREATE_PROPOSAL,
        Permission.AI_CHANGE_STAGE,
        Permission.AI_CHAT,
        Permission.INTEGRATIONS_READ,
        Permission.INTEGRATIONS_WRITE,
        Permission.INTEGRATIONS_WEBHOOKS,
        Permission.USERS_READ,
        Permission.AUDIT_LOGS,
    },
    RoleEnum.ADMIN: {
        Permission.LEADS_READ,
        Permission.LEADS_WRITE,
        Permission.LEADS_DELETE,
        Permission.LEADS_ASSIGN,
        Permission.LEADS_EXPORT,
        Permission.CONTACTS_READ,
        Permission.CONTACTS_WRITE,
        Permission.CONTACTS_DELETE,
        Permission.CONTACTS_IMPORT,
        Permission.COMPANIES_READ,
        Permission.COMPANIES_WRITE,
        Permission.COMPANIES_DELETE,
        Permission.DEALS_READ,
        Permission.DEALS_WRITE,
        Permission.DEALS_DELETE,
        Permission.DEALS_PIPELINE_MANAGE,
        Permission.TASKS_READ,
        Permission.TASKS_WRITE,
        Permission.TASKS_DELETE,
        Permission.CAMPAIGNS_READ,
        Permission.CAMPAIGNS_WRITE,
        Permission.CAMPAIGNS_DELETE,
        Permission.CAMPAIGNS_SEND,
        Permission.CAMPAIGNS_ANALYTICS,
        Permission.CAMPAIGNS_AUDIENCE,
        Permission.CAMPAIGNS_TEMPLATE,
        Permission.CAMPAIGNS_SEQUENCE,
        Permission.CAMPAIGNS_TRIGGER,
        Permission.AI_READ_LEADS,
        Permission.AI_SCORE_LEADS,
        Permission.AI_ASSIGN_LEADS,
        Permission.AI_DRAFT_EMAIL,
        Permission.AI_SEND_EMAIL,
        Permission.AI_SCHEDULE_EMAIL,
        Permission.AI_READ_REPLIES,
        Permission.AI_RESPOND_EMAIL,
        Permission.AI_CREATE_PROPOSAL,
        Permission.AI_CHANGE_STAGE,
        Permission.AI_CHAT,
        Permission.INTEGRATIONS_READ,
        Permission.INTEGRATIONS_WRITE,
        Permission.INTEGRATIONS_WEBHOOKS,
        Permission.USERS_READ,
        Permission.USERS_WRITE,
        Permission.TENANT_SETTINGS,
        Permission.BILLING_READ,
        Permission.AUDIT_LOGS,
        Permission.FEATURE_AI_SCORING,
        Permission.FEATURE_AI_MINER,
        Permission.FEATURE_CAMPAIGNS,
        Permission.FEATURE_WHATSAPP,
    },
    RoleEnum.OWNER: {
        # All permissions
        *ALL_PERMISSIONS,
    },
}


def get_role_permissions(role: RoleEnum) -> Set[Permission]:
    """Get all permissions for a role (including inherited)."""
    permissions = set()
    role_level = ROLE_HIERARCHY.get(role, 0)
    for r, perms in ROLE_PERMISSIONS.items():
        if ROLE_HIERARCHY.get(r, 0) <= role_level:
            permissions.update(perms)
    return permissions


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
    authorization: Optional[str] = Header(None),
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
        if permission.value.startswith("feature:"):
            feature_key = permission.value.replace("feature:", "")
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