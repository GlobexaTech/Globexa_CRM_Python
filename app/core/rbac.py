"""RBAC (Role-Based Access Control) system for Globexa CRM.

Defines permissions, role-permission mappings, and authorization helpers.
"""
from typing import Dict, List, Set, Optional
from enum import Enum
from dataclasses import dataclass
from functools import lru_cache

from app.models import RoleEnum


class Permission(str, Enum):
    """System permissions - fine-grained access control."""
    
    # Tenant management
    TENANT_READ = "tenant:read"
    TENANT_UPDATE = "tenant:update"
    TENANT_DELETE = "tenant:delete"
    TENANT_MANAGE_USERS = "tenant:manage_users"
    TENANT_MANAGE_ROLES = "tenant:manage_roles"
    TENANT_MANAGE_INTEGRATIONS = "tenant:manage_integrations"
    TENANT_MANAGE_SETTINGS = "tenant:manage_settings"
    TENANT_VIEW_BILLING = "tenant:view_billing"
    TENANT_MANAGE_BILLING = "tenant:manage_billing"
    
    # User management
    USER_READ = "user:read"
    USER_CREATE = "user:create"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_MANAGE_ROLES = "user:manage_roles"
    
    # Contacts
    CONTACT_READ = "contact:read"
    CONTACT_CREATE = "contact:create"
    CONTACT_UPDATE = "contact:update"
    CONTACT_DELETE = "contact:delete"
    CONTACT_IMPORT = "contact:import"
    CONTACT_EXPORT = "contact:export"
    
    # Companies
    COMPANY_READ = "company:read"
    COMPANY_CREATE = "company:create"
    COMPANY_UPDATE = "company:update"
    COMPANY_DELETE = "company:delete"
    
    # Leads
    LEAD_READ = "lead:read"
    LEAD_CREATE = "lead:create"
    LEAD_UPDATE = "lead:update"
    LEAD_DELETE = "lead:delete"
    LEAD_ASSIGN = "lead:assign"
    LEAD_CRAWL = "lead:crawl"
    LEAD_ENRICH = "lead:enrich"
    LEAD_EXPORT = "lead:export"
    
    # Deals
    DEAL_READ = "deal:read"
    DEAL_CREATE = "deal:create"
    DEAL_UPDATE = "deal:update"
    DEAL_DELETE = "deal:delete"
    DEAL_MANAGE_PIPELINE = "deal:manage_pipeline"
    
    # Pipelines
    PIPELINE_READ = "pipeline:read"
    PIPELINE_CREATE = "pipeline:create"
    PIPELINE_UPDATE = "pipeline:update"
    PIPELINE_DELETE = "pipeline:delete"
    PIPELINE_MANAGE_STAGES = "pipeline:manage_stages"
    
    # Tasks
    TASK_READ = "task:read"
    TASK_CREATE = "task:create"
    TASK_UPDATE = "task:update"
    TASK_DELETE = "task:delete"
    TASK_ASSIGN = "task:assign"
    
    # Notes
    NOTE_READ = "note:read"
    NOTE_CREATE = "note:create"
    NOTE_UPDATE = "note:update"
    NOTE_DELETE = "note:delete"
    
    # Activities
    ACTIVITY_READ = "activity:read"
    ACTIVITY_CREATE = "activity:create"
    
    # Campaigns
    CAMPAIGN_READ = "campaign:read"
    CAMPAIGN_CREATE = "campaign:create"
    CAMPAIGN_UPDATE = "campaign:update"
    CAMPAIGN_DELETE = "campaign:delete"
    CAMPAIGN_LAUNCH = "campaign:launch"
    CAMPAIGN_SEND = "campaign:send"
    CAMPAIGN_ANALYTICS = "campaign:analytics"
    
    # Integrations
    INTEGRATION_READ = "integration:read"
    INTEGRATION_CREATE = "integration:create"
    INTEGRATION_UPDATE = "integration:update"
    INTEGRATION_DELETE = "integration:delete"
    INTEGRATION_MANAGE_CREDENTIALS = "integration:manage_credentials"
    INTEGRATION_SYNC = "integration:sync"
    INTEGRATION_WEBHOOKS = "integration:webhooks"
    
    # AI
    AI_READ = "ai:read"
    AI_USE = "ai:use"
    AI_CONFIGURE = "ai:configure"
    AI_USAGE_LOGS = "ai:usage_logs"
    
    # Reports/Analytics
    REPORTS_READ = "reports:read"
    REPORTS_CREATE = "reports:create"
    REPORTS_EXPORT = "reports:export"
    
    # Audit
    AUDIT_READ = "audit:read"


# Role to permissions mapping
ROLE_PERMISSIONS: Dict[RoleEnum, Set[Permission]] = {
    RoleEnum.OWNER: {
        # All permissions
        *[
            Permission.TENANT_READ, Permission.TENANT_UPDATE, Permission.TENANT_DELETE,
            Permission.TENANT_MANAGE_USERS, Permission.TENANT_MANAGE_ROLES,
            Permission.TENANT_MANAGE_INTEGRATIONS, Permission.TENANT_MANAGE_SETTINGS,
            Permission.TENANT_VIEW_BILLING, Permission.TENANT_MANAGE_BILLING,
            Permission.USER_READ, Permission.USER_CREATE, Permission.USER_UPDATE,
            Permission.USER_DELETE, Permission.USER_MANAGE_ROLES,
            Permission.CONTACT_READ, Permission.CONTACT_CREATE, Permission.CONTACT_UPDATE,
            Permission.CONTACT_DELETE, Permission.CONTACT_IMPORT, Permission.CONTACT_EXPORT,
            Permission.COMPANY_READ, Permission.COMPANY_CREATE, Permission.COMPANY_UPDATE,
            Permission.COMPANY_DELETE,
            Permission.LEAD_READ, Permission.LEAD_CREATE, Permission.LEAD_UPDATE,
            Permission.LEAD_DELETE, Permission.LEAD_ASSIGN, Permission.LEAD_CRAWL,
            Permission.LEAD_ENRICH, Permission.LEAD_EXPORT,
            Permission.DEAL_READ, Permission.DEAL_CREATE, Permission.DEAL_UPDATE,
            Permission.DEAL_DELETE, Permission.DEAL_MANAGE_PIPELINE,
            Permission.PIPELINE_READ, Permission.PIPELINE_CREATE, Permission.PIPELINE_UPDATE,
            Permission.PIPELINE_DELETE, Permission.PIPELINE_MANAGE_STAGES,
            Permission.TASK_READ, Permission.TASK_CREATE, Permission.TASK_UPDATE,
            Permission.TASK_DELETE, Permission.TASK_ASSIGN,
            Permission.NOTE_READ, Permission.NOTE_CREATE, Permission.NOTE_UPDATE,
            Permission.NOTE_DELETE,
            Permission.ACTIVITY_READ, Permission.ACTIVITY_CREATE,
            Permission.CAMPAIGN_READ, Permission.CAMPAIGN_CREATE, Permission.CAMPAIGN_UPDATE,
            Permission.CAMPAIGN_DELETE, Permission.CAMPAIGN_LAUNCH, Permission.CAMPAIGN_SEND,
            Permission.CAMPAIGN_ANALYTICS,
            Permission.INTEGRATION_READ, Permission.INTEGRATION_CREATE,
            Permission.INTEGRATION_UPDATE, Permission.INTEGRATION_DELETE,
            Permission.INTEGRATION_MANAGE_CREDENTIALS, Permission.INTEGRATION_SYNC,
            Permission.INTEGRATION_WEBHOOKS,
            Permission.AI_READ, Permission.AI_USE, Permission.AI_CONFIGURE,
            Permission.AI_USAGE_LOGS,
            Permission.REPORTS_READ, Permission.REPORTS_CREATE, Permission.REPORTS_EXPORT,
            Permission.AUDIT_READ,
        ]
    },
    
    RoleEnum.ADMIN: {
        Permission.TENANT_READ, Permission.TENANT_UPDATE,
        Permission.TENANT_MANAGE_USERS, Permission.TENANT_MANAGE_ROLES,
        Permission.TENANT_MANAGE_INTEGRATIONS, Permission.TENANT_MANAGE_SETTINGS,
        Permission.TENANT_VIEW_BILLING,
        Permission.USER_READ, Permission.USER_CREATE, Permission.USER_UPDATE,
        Permission.USER_DELETE, Permission.USER_MANAGE_ROLES,
        Permission.CONTACT_READ, Permission.CONTACT_CREATE, Permission.CONTACT_UPDATE,
        Permission.CONTACT_DELETE, Permission.CONTACT_IMPORT, Permission.CONTACT_EXPORT,
        Permission.COMPANY_READ, Permission.COMPANY_CREATE, Permission.COMPANY_UPDATE,
        Permission.COMPANY_DELETE,
        Permission.LEAD_READ, Permission.LEAD_CREATE, Permission.LEAD_UPDATE,
        Permission.LEAD_DELETE, Permission.LEAD_ASSIGN, Permission.LEAD_CRAWL,
        Permission.LEAD_ENRICH, Permission.LEAD_EXPORT,
        Permission.DEAL_READ, Permission.DEAL_CREATE, Permission.DEAL_UPDATE,
        Permission.DEAL_DELETE, Permission.DEAL_MANAGE_PIPELINE,
        Permission.PIPELINE_READ, Permission.PIPELINE_CREATE, Permission.PIPELINE_UPDATE,
        Permission.PIPELINE_DELETE, Permission.PIPELINE_MANAGE_STAGES,
        Permission.TASK_READ, Permission.TASK_CREATE, Permission.TASK_UPDATE,
        Permission.TASK_DELETE, Permission.TASK_ASSIGN,
        Permission.NOTE_READ, Permission.NOTE_CREATE, Permission.NOTE_UPDATE,
        Permission.NOTE_DELETE,
        Permission.ACTIVITY_READ, Permission.ACTIVITY_CREATE,
        Permission.CAMPAIGN_READ, Permission.CAMPAIGN_CREATE, Permission.CAMPAIGN_UPDATE,
        Permission.CAMPAIGN_DELETE, Permission.CAMPAIGN_LAUNCH, Permission.CAMPAIGN_SEND,
        Permission.CAMPAIGN_ANALYTICS,
        Permission.INTEGRATION_READ, Permission.INTEGRATION_CREATE,
        Permission.INTEGRATION_UPDATE, Permission.INTEGRATION_DELETE,
        Permission.INTEGRATION_MANAGE_CREDENTIALS, Permission.INTEGRATION_SYNC,
        Permission.INTEGRATION_WEBHOOKS,
        Permission.AI_READ, Permission.AI_USE, Permission.AI_CONFIGURE,
        Permission.AI_USAGE_LOGS,
        Permission.REPORTS_READ, Permission.REPORTS_CREATE, Permission.REPORTS_EXPORT,
        Permission.AUDIT_READ,
    },
    
    RoleEnum.SALES_MANAGER: {
        Permission.TENANT_READ,
        Permission.USER_READ,
        Permission.CONTACT_READ, Permission.CONTACT_CREATE, Permission.CONTACT_UPDATE,
        Permission.CONTACT_DELETE, Permission.CONTACT_IMPORT, Permission.CONTACT_EXPORT,
        Permission.COMPANY_READ, Permission.COMPANY_CREATE, Permission.COMPANY_UPDATE,
        Permission.LEAD_READ, Permission.LEAD_CREATE, Permission.LEAD_UPDATE,
        Permission.LEAD_ASSIGN, Permission.LEAD_CRAWL, Permission.LEAD_ENRICH,
        Permission.LEAD_EXPORT,
        Permission.DEAL_READ, Permission.DEAL_CREATE, Permission.DEAL_UPDATE,
        Permission.DEAL_DELETE, Permission.DEAL_MANAGE_PIPELINE,
        Permission.PIPELINE_READ, Permission.PIPELINE_CREATE, Permission.PIPELINE_UPDATE,
        Permission.PIPELINE_MANAGE_STAGES,
        Permission.TASK_READ, Permission.TASK_CREATE, Permission.TASK_UPDATE,
        Permission.TASK_DELETE, Permission.TASK_ASSIGN,
        Permission.NOTE_READ, Permission.NOTE_CREATE, Permission.NOTE_UPDATE,
        Permission.NOTE_DELETE,
        Permission.ACTIVITY_READ, Permission.ACTIVITY_CREATE,
        Permission.CAMPAIGN_READ, Permission.CAMPAIGN_CREATE, Permission.CAMPAIGN_UPDATE,
        Permission.CAMPAIGN_LAUNCH, Permission.CAMPAIGN_SEND,
        Permission.CAMPAIGN_ANALYTICS,
        Permission.INTEGRATION_READ, Permission.INTEGRATION_SYNC,
        Permission.AI_READ, Permission.AI_USE,
        Permission.REPORTS_READ, Permission.REPORTS_CREATE,
    },
    
    RoleEnum.SALES_EXECUTIVE: {
        Permission.TENANT_READ,
        Permission.CONTACT_READ, Permission.CONTACT_CREATE, Permission.CONTACT_UPDATE,
        Permission.CONTACT_EXPORT,
        Permission.COMPANY_READ, Permission.COMPANY_CREATE, Permission.COMPANY_UPDATE,
        Permission.LEAD_READ, Permission.LEAD_CREATE, Permission.LEAD_UPDATE,
        Permission.LEAD_ENRICH,
        Permission.DEAL_READ, Permission.DEAL_CREATE, Permission.DEAL_UPDATE,
        Permission.PIPELINE_READ,
        Permission.TASK_READ, Permission.TASK_CREATE, Permission.TASK_UPDATE,
        Permission.TASK_ASSIGN,
        Permission.NOTE_READ, Permission.NOTE_CREATE, Permission.NOTE_UPDATE,
        Permission.ACTIVITY_READ, Permission.ACTIVITY_CREATE,
        Permission.CAMPAIGN_READ,
        Permission.INTEGRATION_READ,
        Permission.AI_READ, Permission.AI_USE,
        Permission.REPORTS_READ,
    },
    
    RoleEnum.MARKETING: {
        Permission.TENANT_READ,
        Permission.CONTACT_READ, Permission.CONTACT_CREATE, Permission.CONTACT_UPDATE,
        Permission.CONTACT_EXPORT,
        Permission.COMPANY_READ, Permission.COMPANY_CREATE, Permission.COMPANY_UPDATE,
        Permission.LEAD_READ, Permission.LEAD_CREATE, Permission.LEAD_UPDATE,
        Permission.LEAD_CRAWL, Permission.LEAD_ENRICH,
        Permission.CAMPAIGN_READ, Permission.CAMPAIGN_CREATE, Permission.CAMPAIGN_UPDATE,
        Permission.CAMPAIGN_LAUNCH, Permission.CAMPAIGN_SEND,
        Permission.CAMPAIGN_ANALYTICS,
        Permission.INTEGRATION_READ,
        Permission.AI_READ, Permission.AI_USE,
        Permission.REPORTS_READ, Permission.REPORTS_CREATE,
    },
    
    RoleEnum.VIEWER: {
        Permission.TENANT_READ,
        Permission.CONTACT_READ,
        Permission.COMPANY_READ,
        Permission.LEAD_READ,
        Permission.DEAL_READ,
        Permission.PIPELINE_READ,
        Permission.TASK_READ,
        Permission.NOTE_READ,
        Permission.ACTIVITY_READ,
        Permission.CAMPAIGN_READ,
        Permission.INTEGRATION_READ,
        Permission.AI_READ,
        Permission.REPORTS_READ,
    },
}


@dataclass
class PermissionCheck:
    """Result of a permission check."""
    allowed: bool
    required_permission: Optional[Permission] = None
    user_role: Optional[RoleEnum] = None
    reason: Optional[str] = None


class RBACService:
    """Service for checking permissions based on user role."""
    
    def __init__(self):
        self._role_permissions = ROLE_PERMISSIONS
    
    def get_permissions_for_role(self, role: RoleEnum) -> Set[Permission]:
        """Get all permissions for a role."""
        return self._role_permissions.get(role, set())
    
    def has_permission(self, role: RoleEnum, permission: Permission) -> bool:
        """Check if a role has a specific permission."""
        role_perms = self._role_permissions.get(role, set())
        return permission in role_perms
    
    def check_permission(
        self, 
        role: RoleEnum, 
        permission: Permission,
        resource_owner_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> PermissionCheck:
        """Check permission with optional resource ownership check."""
        has_perm = self.has_permission(role, permission)
        
        if not has_perm:
            return PermissionCheck(
                allowed=False,
                required_permission=permission,
                user_role=role,
                reason=f"Role {role.value} does not have permission {permission.value}",
            )
        
        # Additional ownership checks for certain permissions
        # (e.g., users can only update their own tasks unless they have admin role)
        # This would be implemented per-resource
        
        return PermissionCheck(allowed=True, required_permission=permission, user_role=role)
    
    def check_permissions(
        self, 
        role: RoleEnum, 
        permissions: List[Permission],
    ) -> PermissionCheck:
        """Check multiple permissions - all must pass."""
        for perm in permissions:
            result = self.check_permission(role, perm)
            if not result.allowed:
                return result
        return PermissionCheck(allowed=True)


# Global RBAC service instance
_rbac_service: Optional[RBACService] = None


def get_rbac_service() -> RBACService:
    """Get the global RBAC service instance."""
    global _rbac_service
    if _rbac_service is None:
        _rbac_service = RBACService()
    return _rbac_service


# FastAPI dependency for permission checking
def require_permission(permission: Permission):
    """FastAPI dependency that checks if the current user has a permission."""
    from fastapi import Depends, HTTPException, status
    from app.api.v1.auth import get_current_user
    from app.models import User
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.database import get_db
    
    async def permission_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        # Get user's role in current tenant
        from app.middleware.tenant import get_current_tenant_id
        from app.models import Membership
        from sqlalchemy import select
        
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenant context"
            )
        
        result = await db.execute(
            select(Membership).where(
                Membership.user_id == current_user.id,
                Membership.tenant_id == tenant_id,
            )
        )
        membership = result.scalar_one_or_none()
        
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this tenant"
            )
        
        rbac = get_rbac_service()
        check = rbac.check_permission(membership.role, permission)
        
        if not check.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value}",
            )
        
        return current_user
    
    return permission_checker


def require_any_permission(*permissions: Permission):
    """FastAPI dependency that checks if user has ANY of the given permissions."""
    from fastapi import Depends, HTTPException, status
    from app.api.v1.auth import get_current_user
    from app.models import User, Membership
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.database import get_db
    from sqlalchemy import select
    
    async def permission_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        from app.middleware.tenant import get_current_tenant_id
        
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenant context"
            )
        
        result = await db.execute(
            select(Membership).where(
                Membership.user_id == current_user.id,
                Membership.tenant_id == tenant_id,
            )
        )
        membership = result.scalar_one_or_none()
        
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this tenant"
            )
        
        rbac = get_rbac_service()
        
        for perm in permissions:
            check = rbac.check_permission(membership.role, perm)
            if check.allowed:
                return current_user
        
        perm_list = ", ".join(p.value for p in permissions)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: requires one of [{perm_list}]",
        )
    
    return permission_checker


# Permission groups for common operations
PERMISSION_GROUPS = {
    "tenant_admin": [
        Permission.TENANT_MANAGE_USERS,
        Permission.TENANT_MANAGE_ROLES,
        Permission.TENANT_MANAGE_INTEGRATIONS,
        Permission.TENANT_MANAGE_SETTINGS,
        Permission.TENANT_VIEW_BILLING,
    ],
    "user_management": [
        Permission.USER_CREATE,
        Permission.USER_UPDATE,
        Permission.USER_DELETE,
        Permission.USER_MANAGE_ROLES,
    ],
    "lead_management": [
        Permission.LEAD_CREATE,
        Permission.LEAD_UPDATE,
        Permission.LEAD_DELETE,
        Permission.LEAD_ASSIGN,
        Permission.LEAD_CRAWL,
        Permission.LEAD_ENRICH,
    ],
    "deal_management": [
        Permission.DEAL_CREATE,
        Permission.DEAL_UPDATE,
        Permission.DEAL_DELETE,
        Permission.DEAL_MANAGE_PIPELINE,
    ],
    "campaign_management": [
        Permission.CAMPAIGN_CREATE,
        Permission.CAMPAIGN_UPDATE,
        Permission.CAMPAIGN_DELETE,
        Permission.CAMPAIGN_LAUNCH,
        Permission.CAMPAIGN_SEND,
    ],
    "integration_management": [
        Permission.INTEGRATION_CREATE,
        Permission.INTEGRATION_UPDATE,
        Permission.INTEGRATION_DELETE,
        Permission.INTEGRATION_MANAGE_CREDENTIALS,
        Permission.INTEGRATION_WEBHOOKS,
    ],
}