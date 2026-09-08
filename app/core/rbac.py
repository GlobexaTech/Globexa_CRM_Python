"""Authoritative roles and permissions shared by APIs, workers and AI tools."""
from typing import Set
from app.models import RoleEnum

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
    """Role membership is explicit; unrelated peer roles do not inherit privileges."""
    return set(ROLE_PERMISSIONS.get(role, set()))



ROLE_PERMISSIONS[RoleEnum.AI_AGENT] = {Permission.LEADS_READ, Permission.AI_CHAT}
ROLE_HIERARCHY[RoleEnum.AI_AGENT] = 0

def may_assign_role(actor, target):
    return actor == RoleEnum.OWNER or (actor == RoleEnum.ADMIN and target not in {RoleEnum.OWNER, RoleEnum.ADMIN})
