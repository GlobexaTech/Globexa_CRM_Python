"""
Role-Based Access Control (RBAC) System

Single authoritative permission system for Globexa CRM.
Consolidates all permission checks into one consistent implementation.
"""

from enum import Enum
from typing import Set, Dict, List, Optional
from dataclasses import dataclass, field

from app.models import RoleEnum


class Permission(str, Enum):
    """Granular permissions for the CRM system."""
    # User management
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_LIST = "user:list"
    
    # Tenant management
    TENANT_CREATE = "tenant:create"
    TENANT_READ = "tenant:read"
    TENANT_UPDATE = "tenant:update"
    TENANT_DELETE = "tenant:delete"
    TENANT_SETTINGS = "tenant:settings"
    
    # Membership management
    MEMBERSHIP_CREATE = "membership:create"
    MEMBERSHIP_READ = "membership:read"
    MEMBERSHIP_UPDATE = "membership:update"
    MEMBERSHIP_DELETE = "membership:delete"
    
    # Role management
    ROLE_ASSIGN = "role:assign"
    ROLE_ESCALATE = "role:escalate"
    
    # CRM data
    CONTACT_CREATE = "contact:create"
    CONTACT_READ = "contact:read"
    CONTACT_UPDATE = "contact:update"
    CONTACT_DELETE = "contact:delete"
    CONTACT_LIST = "contact:list"
    CONTACT_IMPORT = "contact:import"
    CONTACT_EXPORT = "contact:export"
    
    COMPANY_CREATE = "company:create"
    COMPANY_READ = "company:read"
    COMPANY_UPDATE = "company:update"
    COMPANY_DELETE = "company:delete"
    COMPANY_LIST = "company:list"
    
    LEAD_CREATE = "lead:create"
    LEAD_READ = "lead:read"
    LEAD_UPDATE = "lead:update"
    LEAD_DELETE = "lead:delete"
    LEAD_LIST = "lead:list"
    LEAD_ASSIGN = "lead:assign"
    LEAD_QUALIFY = "lead:qualify"
    LEAD_CONVERT = "lead:convert"
    LEAD_IMPORT = "lead:import"
    LEAD_EXPORT = "lead:export"
    
    DEAL_CREATE = "deal:create"
    DEAL_READ = "deal:read"
    DEAL_UPDATE = "deal:update"
    DEAL_DELETE = "deal:delete"
    DEAL_LIST = "deal:list"
    DEAL_CLOSE = "deal:close"
    
    PIPELINE_CREATE = "pipeline:create"
    PIPELINE_READ = "pipeline:read"
    PIPELINE_UPDATE = "pipeline:update"
    PIPELINE_DELETE = "pipeline:delete"
    
    TASK_CREATE = "task:create"
    TASK_READ = "task:read"
    TASK_UPDATE = "task:update"
    TASK_DELETE = "task:delete"
    TASK_LIST = "task:list"
    TASK_ASSIGN = "task:assign"
    
    NOTE_CREATE = "note:create"
    NOTE_READ = "note:read"
    NOTE_UPDATE = "note:update"
    NOTE_DELETE = "note:delete"
    NOTE_LIST = "note:list"
    
    ACTIVITY_READ = "activity:read"
    ACTIVITY_LIST = "activity:list"
    
    PROPOSAL_CREATE = "proposal:create"
    PROPOSAL_READ = "proposal:read"
    PROPOSAL_UPDATE = "proposal:update"
    PROPOSAL_DELETE = "proposal:delete"
    PROPOSAL_SEND = "proposal:send"
    
    PRODUCT_CREATE = "product:create"
    PRODUCT_READ = "product:read"
    PRODUCT_UPDATE = "product:update"
    PRODUCT_DELETE = "product:delete"
    
    # Campaigns
    CAMPAIGN_CREATE = "campaign:create"
    CAMPAIGN_READ = "campaign:read"
    CAMPAIGN_UPDATE = "campaign:update"
    CAMPAIGN_DELETE = "campaign:delete"
    CAMPAIGN_LIST = "campaign:list"
    CAMPAIGN_SEND = "campaign:send"
    CAMPAIGN_SCHEDULE = "campaign:schedule"
    CAMPAIGN_ANALYTICS = "campaign:analytics"
    
    # Email
    EMAIL_SEND = "email:send"
    EMAIL_TEMPLATE_CREATE = "email:template:create"
    EMAIL_TEMPLATE_READ = "email:template:read"
    EMAIL_TEMPLATE_UPDATE = "email:template:update"
    EMAIL_TEMPLATE_DELETE = "email:template:delete"
    SENDING_DOMAIN_MANAGE = "sending_domain:manage"
    
    # Integrations
    INTEGRATION_CREATE = "integration:create"
    INTEGRATION_READ = "integration:read"
    INTEGRATION_UPDATE = "integration:update"
    INTEGRATION_DELETE = "integration:delete"
    INTEGRATION_SYNC = "integration:sync"
    INTEGRATION_CREDENTIALS_VIEW = "integration:credentials:view"
    INTEGRATION_CREDENTIALS_MANAGE = "integration:credentials:manage"
    WEBHOOK_CREATE = "webhook:create"
    WEBHOOK_READ = "webhook:read"
    WEBHOOK_UPDATE = "webhook:update"
    WEBHOOK_DELETE = "webhook:delete"
    
    # AI
    AI_USE = "ai:use"
    AI_CONFIGURE = "ai:configure"
    AI_COST_VIEW = "ai:cost:view"
    AI_USAGE_VIEW = "ai:usage:view"
    
    # Analytics/Reports
    REPORT_VIEW = "report:view"
    REPORT_CREATE = "report:create"
    REPORT_EXPORT = "report:export"
    ATTRIBUTION_VIEW = "attribution:view"
    ATTRIBUTION_CONFIGURE = "attribution:configure"
    
    # Audit/Security
    AUDIT_LOG_VIEW = "audit:log:view"
    SECURITY_SETTINGS = "security:settings"
    
    # Billing/Subscription
    SUBSCRIPTION_VIEW = "subscription:view"
    SUBSCRIPTION_MANAGE = "subscription:manage"
    USAGE_VIEW = "usage:view"
    
    # Admin/Superuser
    SUPERUSER_ALL = "superuser:*"


# Role to permissions mapping
ROLE_PERMISSIONS: Dict[RoleEnum, Set[Permission]] = {
    RoleEnum.OWNER: {
        # Owner has all permissions
        Permission.SUPERUSER_ALL,
    },
    
    RoleEnum.ADMIN: {
        # Admin has most permissions except superuser
        Permission.USER_CREATE,
        Permission.USER_READ,
        Permission.USER_UPDATE,
        Permission.USER_DELETE,
        Permission.USER_LIST,
        Permission.TENANT_READ,
        Permission.TENANT_UPDATE,
        Permission.TENANT_SETTINGS,
        Permission.MEMBERSHIP_CREATE,
        Permission.MEMBERSHIP_READ,
        Permission.MEMBERSHIP_UPDATE,
        Permission.MEMBERSHIP_DELETE,
        Permission.ROLE_ASSIGN,  # Can assign roles except OWNER
        Permission.CONTACT_CREATE,
        Permission.CONTACT_READ,
        Permission.CONTACT_UPDATE,
        Permission.CONTACT_DELETE,
        Permission.CONTACT_LIST,
        Permission.CONTACT_IMPORT,
        Permission.CONTACT_EXPORT,
        Permission.COMPANY_CREATE,
        Permission.COMPANY_READ,
        Permission.COMPANY_UPDATE,
        Permission.COMPANY_DELETE,
        Permission.COMPANY_LIST,
        Permission.LEAD_CREATE,
        Permission.LEAD_READ,
        Permission.LEAD_UPDATE,
        Permission.LEAD_DELETE,
        Permission.LEAD_LIST,
        Permission.LEAD_ASSIGN,
        Permission.LEAD_QUALIFY,
        Permission.LEAD_CONVERT,
        Permission.LEAD_IMPORT,
        Permission.LEAD_EXPORT,
        Permission.DEAL_CREATE,
        Permission.DEAL_READ,
        Permission.DEAL_UPDATE,
        Permission.DEAL_DELETE,
        Permission.DEAL_LIST,
        Permission.DEAL_CLOSE,
        Permission.PIPELINE_CREATE,
        Permission.PIPELINE_READ,
        Permission.PIPELINE_UPDATE,
        Permission.PIPELINE_DELETE,
        Permission.TASK_CREATE,
        Permission.TASK_READ,
        Permission.TASK_UPDATE,
        Permission.TASK_DELETE,
        Permission.TASK_LIST,
        Permission.TASK_ASSIGN,
        Permission.NOTE_CREATE,
        Permission.NOTE_READ,
        Permission.NOTE_UPDATE,
        Permission.NOTE_DELETE,
        Permission.NOTE_LIST,
        Permission.ACTIVITY_READ,
        Permission.ACTIVITY_LIST,
        Permission.PROPOSAL_CREATE,
        Permission.PROPOSAL_READ,
        Permission.PROPOSAL_UPDATE,
        Permission.PROPOSAL_DELETE,
        Permission.PROPOSAL_SEND,
        Permission.PRODUCT_CREATE,
        Permission.PRODUCT_READ,
        Permission.PRODUCT_UPDATE,
        Permission.PRODUCT_DELETE,
        Permission.CAMPAIGN_CREATE,
        Permission.CAMPAIGN_READ,
        Permission.CAMPAIGN_UPDATE,
        Permission.CAMPAIGN_DELETE,
        Permission.CAMPAIGN_LIST,
        Permission.CAMPAIGN_SEND,
        Permission.CAMPAIGN_SCHEDULE,
        Permission.CAMPAIGN_ANALYTICS,
        Permission.EMAIL_SEND,
        Permission.EMAIL_TEMPLATE_CREATE,
        Permission.EMAIL_TEMPLATE_READ,
        Permission.EMAIL_TEMPLATE_UPDATE,
        Permission.EMAIL_TEMPLATE_DELETE,
        Permission.SENDING_DOMAIN_MANAGE,
        Permission.INTEGRATION_CREATE,
        Permission.INTEGRATION_READ,
        Permission.INTEGRATION_UPDATE,
        Permission.INTEGRATION_DELETE,
        Permission.INTEGRATION_SYNC,
        Permission.INTEGRATION_CREDENTIALS_VIEW,
        Permission.INTEGRATION_CREDENTIALS_MANAGE,
        Permission.WEBHOOK_CREATE,
        Permission.WEBHOOK_READ,
        Permission.WEBHOOK_UPDATE,
        Permission.WEBHOOK_DELETE,
        Permission.AI_USE,
        Permission.AI_CONFIGURE,
        Permission.AI_COST_VIEW,
        Permission.AI_USAGE_VIEW,
        Permission.REPORT_VIEW,
        Permission.REPORT_CREATE,
        Permission.REPORT_EXPORT,
        Permission.ATTRIBUTION_VIEW,
        Permission.ATTRIBUTION_CONFIGURE,
        Permission.AUDIT_LOG_VIEW,
        Permission.SECURITY_SETTINGS,
        Permission.SUBSCRIPTION_VIEW,
        Permission.SUBSCRIPTION_MANAGE,
        Permission.USAGE_VIEW,
    },
    
    RoleEnum.SALES_MANAGER: {
        # Sales manager has full CRM access but limited admin
        Permission.USER_READ,
        Permission.USER_LIST,
        Permission.TENANT_READ,
        Permission.MEMBERSHIP_READ,
        Permission.CONTACT_CREATE,
        Permission.CONTACT_READ,
        Permission.CONTACT_UPDATE,
        Permission.CONTACT_DELETE,
        Permission.CONTACT_LIST,
        Permission.CONTACT_IMPORT,
        Permission.CONTACT_EXPORT,
        Permission.COMPANY_CREATE,
        Permission.COMPANY_READ,
        Permission.COMPANY_UPDATE,
        Permission.COMPANY_DELETE,
        Permission.COMPANY_LIST,
        Permission.LEAD_CREATE,
        Permission.LEAD_READ,
        Permission.LEAD_UPDATE,
        Permission.LEAD_DELETE,
        Permission.LEAD_LIST,
        Permission.LEAD_ASSIGN,
        Permission.LEAD_QUALIFY,
        Permission.LEAD_CONVERT,
        Permission.LEAD_IMPORT,
        Permission.LEAD_EXPORT,
        Permission.DEAL_CREATE,
        Permission.DEAL_READ,
        Permission.DEAL_UPDATE,
        Permission.DEAL_DELETE,
        Permission.DEAL_LIST,
        Permission.DEAL_CLOSE,
        Permission.PIPELINE_CREATE,
        Permission.PIPELINE_READ,
        Permission.PIPELINE_UPDATE,
        Permission.TASK_CREATE,
        Permission.TASK_READ,
        Permission.TASK_UPDATE,
        Permission.TASK_DELETE,
        Permission.TASK_LIST,
        Permission.TASK_ASSIGN,
        Permission.NOTE_CREATE,
        Permission.NOTE_READ,
        Permission.NOTE_UPDATE,
        Permission.NOTE_DELETE,
        Permission.NOTE_LIST,
        Permission.ACTIVITY_READ,
        Permission.ACTIVITY_LIST,
        Permission.PROPOSAL_CREATE,
        Permission.PROPOSAL_READ,
        Permission.PROPOSAL_UPDATE,
        Permission.PROPOSAL_DELETE,
        Permission.PROPOSAL_SEND,
        Permission.PRODUCT_CREATE,
        Permission.PRODUCT_READ,
        Permission.PRODUCT_UPDATE,
        Permission.PRODUCT_DELETE,
        Permission.CAMPAIGN_CREATE,
        Permission.CAMPAIGN_READ,
        Permission.CAMPAIGN_UPDATE,
        Permission.CAMPAIGN_DELETE,
        Permission.CAMPAIGN_LIST,
        Permission.CAMPAIGN_SEND,
        Permission.CAMPAIGN_SCHEDULE,
        Permission.CAMPAIGN_ANALYTICS,
        Permission.EMAIL_SEND,
        Permission.EMAIL_TEMPLATE_CREATE,
        Permission.EMAIL_TEMPLATE_READ,
        Permission.EMAIL_TEMPLATE_UPDATE,
        Permission.EMAIL_TEMPLATE_DELETE,
        Permission.SENDING_DOMAIN_MANAGE,
        Permission.INTEGRATION_READ,
        Permission.INTEGRATION_SYNC,
        Permission.AI_USE,
        Permission.AI_COST_VIEW,
        Permission.AI_USAGE_VIEW,
        Permission.REPORT_VIEW,
        Permission.REPORT_CREATE,
        Permission.REPORT_EXPORT,
        Permission.ATTRIBUTION_VIEW,
        Permission.USAGE_VIEW,
    },
    
    RoleEnum.SALES_EXECUTIVE: {
        # Sales executive has standard CRM access
        Permission.USER_READ,
        Permission.TENANT_READ,
        Permission.CONTACT_CREATE,
        Permission.CONTACT_READ,
        Permission.CONTACT_UPDATE,
        Permission.CONTACT_LIST,
        Permission.CONTACT_EXPORT,
        Permission.COMPANY_CREATE,
        Permission.COMPANY_READ,
        Permission.COMPANY_UPDATE,
        Permission.COMPANY_LIST,
        Permission.LEAD_CREATE,
        Permission.LEAD_READ,
        Permission.LEAD_UPDATE,
        Permission.LEAD_LIST,
        Permission.LEAD_QUALIFY,
        Permission.LEAD_CONVERT,
        Permission.DEAL_CREATE,
        Permission.DEAL_READ,
        Permission.DEAL_UPDATE,
        Permission.DEAL_LIST,
        Permission.DEAL_CLOSE,
        Permission.PIPELINE_READ,
        Permission.TASK_CREATE,
        Permission.TASK_READ,
        Permission.TASK_UPDATE,
        Permission.TASK_LIST,
        Permission.NOTE_CREATE,
        Permission.NOTE_READ,
        Permission.NOTE_UPDATE,
        Permission.NOTE_LIST,
        Permission.ACTIVITY_READ,
        Permission.ACTIVITY_LIST,
        Permission.PROPOSAL_CREATE,
        Permission.PROPOSAL_READ,
        Permission.PROPOSAL_UPDATE,
        Permission.PROPOSAL_SEND,
        Permission.PRODUCT_READ,
        Permission.CAMPAIGN_READ,
        Permission.CAMPAIGN_LIST,
        Permission.CAMPAIGN_ANALYTICS,
        Permission.EMAIL_SEND,
        Permission.EMAIL_TEMPLATE_READ,
        Permission.AI_USE,
        Permission.REPORT_VIEW,
        Permission.ATTRIBUTION_VIEW,
        Permission.USAGE_VIEW,
    },
    
    RoleEnum.MARKETING: {
        # Marketing has campaign and contact access
        Permission.USER_READ,
        Permission.TENANT_READ,
        Permission.CONTACT_CREATE,
        Permission.CONTACT_READ,
        Permission.CONTACT_UPDATE,
        Permission.CONTACT_LIST,
        Permission.CONTACT_IMPORT,
        Permission.CONTACT_EXPORT,
        Permission.COMPANY_READ,
        Permission.COMPANY_LIST,
        Permission.LEAD_READ,
        Permission.LEAD_LIST,
        Permission.LEAD_EXPORT,
        Permission.DEAL_READ,
        Permission.DEAL_LIST,
        Permission.PIPELINE_READ,
        Permission.TASK_READ,
        Permission.TASK_LIST,
        Permission.NOTE_READ,
        Permission.NOTE_LIST,
        Permission.ACTIVITY_READ,
        Permission.ACTIVITY_LIST,
        Permission.CAMPAIGN_CREATE,
        Permission.CAMPAIGN_READ,
        Permission.CAMPAIGN_UPDATE,
        Permission.CAMPAIGN_LIST,
        Permission.CAMPAIGN_SEND,
        Permission.CAMPAIGN_SCHEDULE,
        Permission.CAMPAIGN_ANALYTICS,
        Permission.EMAIL_SEND,
        Permission.EMAIL_TEMPLATE_CREATE,
        Permission.EMAIL_TEMPLATE_READ,
        Permission.EMAIL_TEMPLATE_UPDATE,
        Permission.SENDING_DOMAIN_MANAGE,
        Permission.INTEGRATION_READ,
        Permission.AI_USE,
        Permission.REPORT_VIEW,
        Permission.REPORT_CREATE,
        Permission.REPORT_EXPORT,
        Permission.ATTRIBUTION_VIEW,
        Permission.ATTRIBUTION_CONFIGURE,
        Permission.USAGE_VIEW,
    },
    
    RoleEnum.VIEWER: {
        # Viewer has read-only access
        Permission.USER_READ,
        Permission.TENANT_READ,
        Permission.CONTACT_READ,
        Permission.CONTACT_LIST,
        Permission.COMPANY_READ,
        Permission.COMPANY_LIST,
        Permission.LEAD_READ,
        Permission.LEAD_LIST,
        Permission.DEAL_READ,
        Permission.DEAL_LIST,
        Permission.PIPELINE_READ,
        Permission.TASK_READ,
        Permission.TASK_LIST,
        Permission.NOTE_READ,
        Permission.NOTE_LIST,
        Permission.ACTIVITY_READ,
        Permission.ACTIVITY_LIST,
        Permission.PROPOSAL_READ,
        Permission.PRODUCT_READ,
        Permission.CAMPAIGN_READ,
        Permission.CAMPAIGN_LIST,
        Permission.CAMPAIGN_ANALYTICS,
        Permission.EMAIL_TEMPLATE_READ,
        Permission.INTEGRATION_READ,
        Permission.AI_USE,
        Permission.REPORT_VIEW,
        Permission.ATTRIBUTION_VIEW,
        Permission.USAGE_VIEW,
    },
}


class RBAC:
    """Role-Based Access Control service."""
    
    @staticmethod
    def get_permissions(role: RoleEnum) -> Set[Permission]:
        """Get all permissions for a role."""
        return ROLE_PERMISSIONS.get(role, set())
    
    @staticmethod
    def has_permission(role: RoleEnum, permission: Permission) -> bool:
        """Check if role has a specific permission."""
        permissions = RBAC.get_permissions(role)
        return Permission.SUPERUSER_ALL in permissions or permission in permissions
    
    @staticmethod
    def has_any_permission(role: RoleEnum, permissions: List[Permission]) -> bool:
        """Check if role has any of the given permissions."""
        return any(RBAC.has_permission(role, p) for p in permissions)
    
    @staticmethod
    def has_all_permissions(role: RoleEnum, permissions: List[Permission]) -> bool:
        """Check if role has all of the given permissions."""
        return all(RBAC.has_permission(role, p) for p in permissions)
    
    @staticmethod
    def can_assign_role(assigner_role: RoleEnum, target_role: RoleEnum) -> bool:
        """
        Check if assigner can assign target role.
        
        Rules:
        - OWNER can assign any role
        - ADMIN can assign any role except OWNER
        - Others cannot assign roles
        """
        if assigner_role == RoleEnum.OWNER:
            return True
        if assigner_role == RoleEnum.ADMIN and target_role != RoleEnum.OWNER:
            return True
        return False
    
    @staticmethod
    def can_manage_membership(actor_role: RoleEnum, target_role: RoleEnum) -> bool:
        """
        Check if actor can manage membership of target role.
        
        Cannot manage membership of higher or equal role.
        """
        role_hierarchy = {
            RoleEnum.OWNER: 5,
            RoleEnum.ADMIN: 4,
            RoleEnum.SALES_MANAGER: 3,
            RoleEnum.SALES_EXECUTIVE: 2,
            RoleEnum.MARKETING: 2,
            RoleEnum.VIEWER: 1,
        }
        
        actor_level = role_hierarchy.get(actor_role, 0)
        target_level = role_hierarchy.get(target_role, 0)
        
        return actor_level > target_level
    
    @staticmethod
    def get_assignable_roles(actor_role: RoleEnum) -> List[RoleEnum]:
        """Get list of roles actor can assign."""
        all_roles = [
            RoleEnum.ADMIN,
            RoleEnum.SALES_MANAGER,
            RoleEnum.SALES_EXECUTIVE,
            RoleEnum.MARKETING,
            RoleEnum.VIEWER,
        ]
        return [r for r in all_roles if RBAC.can_assign_role(actor_role, r)]


# Dependency for FastAPI routes
def require_permission(permission: Permission):
    """FastAPI dependency to require a specific permission."""
    from fastapi import Depends, HTTPException, status
    from app.api.deps import get_current_user_membership
    
    async def check_permission(membership = Depends(get_current_user_membership)):
        if not RBAC.has_permission(membership.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value}"
            )
        return membership
    
    return check_permission


def require_any_permission(permissions: List[Permission]):
    """FastAPI dependency to require any of the given permissions."""
    from fastapi import Depends, HTTPException, status
    from app.api.deps import get_current_user_membership
    
    async def check_permission(membership = Depends(get_current_user_membership)):
        if not RBAC.has_any_permission(membership.role, permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: requires one of {[p.value for p in permissions]}"
            )
        return membership
    
    return check_permission


def require_role(*roles: RoleEnum):
    """FastAPI dependency to require specific role(s)."""
    from fastapi import Depends, HTTPException, status
    from app.api.deps import get_current_user_membership
    
    async def check_role(membership = Depends(get_current_user_membership)):
        if membership.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: one of {[r.value for r in roles]}"
            )
        return membership
    
    return check_role