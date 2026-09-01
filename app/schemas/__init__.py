"""
Pydantic schemas for Globexa CRM API.
Request/Response models for authentication, tenants, users.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# =============================================================================
# Base schemas
# =============================================================================

class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TimestampMixin(BaseModel):
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Authentication schemas
# =============================================================================

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    tenant_name: Optional[str] = Field(None, max_length=255)
    tenant_slug: Optional[str] = Field(None, max_length=100, pattern=r"^[a-z0-9-]+$")


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class GoogleAuthRequest(BaseModel):
    code: str


class TokenPayload(BaseModel):
    sub: str
    tenant_id: str
    role: str
    email: str
    exp: int
    type: str


# =============================================================================
# User schemas
# =============================================================================

class UserBase(BaseSchema):
    email: EmailStr
    full_name: str
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    timezone: str = "UTC"
    locale: str = "en"
    is_active: bool = True
    is_superuser: bool = False
    email_verified: bool = False


class UserCreate(UserBase):
    hashed_password: Optional[str] = None
    google_id: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=255)
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    timezone: Optional[str] = None
    locale: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase, TimestampMixin):
    id: UUID
    last_login_at: Optional[datetime] = None


class UserWithMemberships(UserResponse):
    memberships: List["MembershipResponse"] = []


# =============================================================================
# Tenant schemas
# =============================================================================

class TenantBase(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    domain: Optional[str] = Field(None, max_length=255)
    logo_url: Optional[str] = None
    settings: Dict[str, Any] = {}
    is_active: bool = True


class TenantCreate(TenantBase):
    pass


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)
    logo_url: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class TenantResponse(TenantBase, TimestampMixin):
    id: UUID


class TenantWithSubscription(TenantResponse):
    subscription: Optional["SubscriptionResponse"] = None
    feature_entitlements: List["FeatureEntitlementResponse"] = []


# =============================================================================
# Membership schemas
# =============================================================================

class MembershipBase(BaseSchema):
    user_id: UUID
    tenant_id: UUID
    role: str
    is_default: bool = False


class MembershipCreate(BaseModel):
    user_id: UUID
    role: str = "sales_executive"
    is_default: bool = False


class MembershipUpdate(BaseModel):
    role: Optional[str] = None
    is_default: Optional[bool] = None


class MembershipResponse(MembershipBase, TimestampMixin):
    id: UUID
    invited_by_id: Optional[UUID] = None
    joined_at: datetime
    user: Optional[UserResponse] = None
    tenant: Optional[TenantResponse] = None


# =============================================================================
# Subscription schemas
# =============================================================================

class SubscriptionBase(BaseSchema):
    tenant_id: UUID
    package: str
    status: str
    billing_email: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    canceled_at: Optional[datetime] = None


class SubscriptionCreate(BaseModel):
    package: str = "starter"
    billing_email: Optional[EmailStr] = None


class SubscriptionUpdate(BaseModel):
    package: Optional[str] = None
    billing_email: Optional[EmailStr] = None
    cancel_at_period_end: Optional[bool] = None


class SubscriptionResponse(SubscriptionBase, TimestampMixin):
    id: UUID


# =============================================================================
# Feature Entitlement schemas
# =============================================================================

class FeatureEntitlementBase(BaseSchema):
    tenant_id: UUID
    feature_key: str
    enabled: bool
    limit_value: Optional[int] = None
    metadata: Dict[str, Any] = {}


class FeatureEntitlementCreate(BaseModel):
    feature_key: str
    enabled: bool = True
    limit_value: Optional[int] = None
    metadata: Dict[str, Any] = {}


class FeatureEntitlementUpdate(BaseModel):
    enabled: Optional[bool] = None
    limit_value: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class FeatureEntitlementResponse(FeatureEntitlementBase, TimestampMixin):
    id: UUID


# =============================================================================
# Usage Record schemas
# =============================================================================

class UsageRecordBase(BaseSchema):
    tenant_id: UUID
    user_id: Optional[UUID] = None
    metric: str
    quantity: int = 1
    period_start: datetime
    period_end: datetime
    metadata: Dict[str, Any] = {}


class UsageRecordCreate(BaseModel):
    metric: str
    quantity: int = 1
    period_start: datetime
    period_end: datetime
    metadata: Dict[str, Any] = {}


class UsageRecordResponse(UsageRecordBase, TimestampMixin):
    id: UUID


# =============================================================================
# Audit Log schemas
# =============================================================================

class AuditLogBase(BaseSchema):
    tenant_id: UUID
    user_id: Optional[UUID] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    correlation_id: Optional[str] = None


class AuditLogResponse(AuditLogBase, TimestampMixin):
    id: UUID


# =============================================================================
# AI Usage Log schemas
# =============================================================================

class AIUsageLogBase(BaseSchema):
    tenant_id: UUID
    user_id: Optional[UUID] = None
    task_type: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: Optional[float] = None
    latency_ms: int = 0
    success: bool = True
    error_message: Optional[str] = None
    tool_actions: Optional[List[str]] = None
    correlation_id: Optional[str] = None


class AIUsageLogCreate(BaseModel):
    task_type: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: Optional[float] = None
    latency_ms: int = 0
    success: bool = True
    error_message: Optional[str] = None
    tool_actions: Optional[List[str]] = None
    correlation_id: Optional[str] = None


class AIUsageLogResponse(AIUsageLogBase, TimestampMixin):
    id: UUID


# =============================================================================
# Pagination
# =============================================================================

class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(cls, items: List[Any], total: int, params: PaginationParams) -> "PaginatedResponse":
        total_pages = (total + params.page_size - 1) // params.page_size
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            total_pages=total_pages,
        )


# =============================================================================
# Health check
# =============================================================================

class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    redis: str
    timestamp: datetime


# =============================================================================
# CRM Schemas (Phase 2)
# =============================================================================

class CompanyBase(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    size: Optional[str] = Field(None, max_length=50)
    annual_revenue: Optional[int] = None
    description: Optional[str] = None
    website: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    facebook_url: Optional[str] = Field(None, max_length=500)
    twitter_url: Optional[str] = Field(None, max_length=500)
    source: Optional[str] = None
    utm_source: Optional[str] = Field(None, max_length=100)
    utm_medium: Optional[str] = Field(None, max_length=100)
    utm_campaign: Optional[str] = Field(None, max_length=100)
    utm_content: Optional[str] = Field(None, max_length=100)
    utm_term: Optional[str] = Field(None, max_length=100)
    custom_fields: Dict[str, Any] = {}


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    size: Optional[str] = Field(None, max_length=50)
    annual_revenue: Optional[int] = None
    description: Optional[str] = None
    website: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    facebook_url: Optional[str] = Field(None, max_length=500)
    twitter_url: Optional[str] = Field(None, max_length=500)
    source: Optional[str] = None
    utm_source: Optional[str] = Field(None, max_length=100)
    utm_medium: Optional[str] = Field(None, max_length=100)
    utm_campaign: Optional[str] = Field(None, max_length=100)
    utm_content: Optional[str] = Field(None, max_length=100)
    utm_term: Optional[str] = Field(None, max_length=100)
    custom_fields: Optional[Dict[str, Any]] = None


class CompanyResponse(CompanyBase, TimestampMixin):
    id: UUID
    ai_summary: Optional[str] = None
    ai_icp_score: Optional[int] = None
    ai_icp_reason: Optional[str] = None
    created_by_id: Optional[UUID] = None
    updated_by_id: Optional[UUID] = None


class ContactBase(BaseSchema):
    company_id: Optional[UUID] = None
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    mobile: Optional[str] = Field(None, max_length=50)
    title: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    is_primary: bool = False
    do_not_contact: bool = False
    email_opted_out: bool = False
    sms_opted_out: bool = False
    source: Optional[str] = None
    utm_source: Optional[str] = Field(None, max_length=100)
    utm_medium: Optional[str] = Field(None, max_length=100)
    utm_campaign: Optional[str] = Field(None, max_length=100)
    utm_content: Optional[str] = Field(None, max_length=100)
    utm_term: Optional[str] = Field(None, max_length=100)
    custom_fields: Dict[str, Any] = {}


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    company_id: Optional[UUID] = None
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    mobile: Optional[str] = Field(None, max_length=50)
    title: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    is_primary: Optional[bool] = None
    do_not_contact: Optional[bool] = None
    email_opted_out: Optional[bool] = None
    sms_opted_out: Optional[bool] = None
    source: Optional[str] = None
    utm_source: Optional[str] = Field(None, max_length=100)
    utm_medium: Optional[str] = Field(None, max_length=100)
    utm_campaign: Optional[str] = Field(None, max_length=100)
    utm_content: Optional[str] = Field(None, max_length=100)
    utm_term: Optional[str] = Field(None, max_length=100)
    custom_fields: Optional[Dict[str, Any]] = None


class ContactResponse(ContactBase, TimestampMixin):
    id: UUID
    ai_summary: Optional[str] = None
    ai_lead_score: Optional[int] = None
    created_by_id: Optional[UUID] = None
    updated_by_id: Optional[UUID] = None
    company: Optional[CompanyResponse] = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class LeadBase(BaseSchema):
    contact_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    status: str = "new"
    owner_id: Optional[UUID] = None
    source: Optional[str] = None
    source_id: Optional[str] = Field(None, max_length=255)
    utm_source: Optional[str] = Field(None, max_length=100)
    utm_medium: Optional[str] = Field(None, max_length=100)
    utm_campaign: Optional[str] = Field(None, max_length=100)
    utm_content: Optional[str] = Field(None, max_length=100)
    utm_term: Optional[str] = Field(None, max_length=100)
    referrer_url: Optional[str] = Field(None, max_length=500)
    landing_page: Optional[str] = Field(None, max_length=500)
    custom_fields: Dict[str, Any] = {}


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    contact_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None
    owner_id: Optional[UUID] = None
    source: Optional[str] = None
    source_id: Optional[str] = Field(None, max_length=255)
    utm_source: Optional[str] = Field(None, max_length=100)
    utm_medium: Optional[str] = Field(None, max_length=100)
    utm_campaign: Optional[str] = Field(None, max_length=100)
    utm_content: Optional[str] = Field(None, max_length=100)
    utm_term: Optional[str] = Field(None, max_length=100)
    referrer_url: Optional[str] = Field(None, max_length=500)
    landing_page: Optional[str] = Field(None, max_length=500)
    ai_score: Optional[int] = Field(None, ge=0, le=100)
    ai_score_reason: Optional[str] = None
    ai_next_action: Optional[str] = None
    ai_next_action_confidence: Optional[float] = Field(None, ge=0, le=1)
    ai_summary: Optional[str] = None
    is_qualified: Optional[bool] = None
    qualification_notes: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None


class LeadResponse(LeadBase, TimestampMixin):
    id: UUID
    ai_score: Optional[int] = None
    ai_score_reason: Optional[str] = None
    ai_next_action: Optional[str] = None
    ai_next_action_confidence: Optional[float] = None
    ai_summary: Optional[str] = None
    is_qualified: bool = False
    qualified_by_id: Optional[UUID] = None
    qualified_at: Optional[datetime] = None
    qualification_notes: Optional[str] = None
    converted_at: Optional[datetime] = None
    converted_deal_id: Optional[UUID] = None
    created_by_id: Optional[UUID] = None
    updated_by_id: Optional[UUID] = None
    owner: Optional[UserResponse] = None
    contact: Optional[ContactResponse] = None
    company: Optional[CompanyResponse] = None


class PipelineBase(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    is_default: bool = False
    is_active: bool = True


class PipelineCreate(PipelineBase):
    pass


class PipelineUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class PipelineResponse(PipelineBase, TimestampMixin):
    id: UUID
    stages: List["StageResponse"] = []


class StageBase(BaseSchema):
    pipeline_id: UUID
    name: str = Field(min_length=1, max_length=100)
    order: int = 0
    probability: int = Field(0, ge=0, le=100)
    is_closed: bool = False
    is_won: bool = False
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")


class StageCreate(StageBase):
    pass


class StageUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    order: Optional[int] = None
    probability: Optional[int] = Field(None, ge=0, le=100)
    is_closed: Optional[bool] = None
    is_won: Optional[bool] = None
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")


class StageResponse(StageBase, TimestampMixin):
    id: UUID
    deals_count: int = 0


class DealBase(BaseSchema):
    pipeline_id: UUID
    stage_id: UUID
    contact_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    value: int = 0
    currency: str = "USD"
    owner_id: Optional[UUID] = None
    expected_close_date: Optional[datetime] = None
    probability: int = Field(0, ge=0, le=100)
    source: Optional[str] = None
    custom_fields: Dict[str, Any] = {}


class DealCreate(DealBase):
    pass


class DealUpdate(BaseModel):
    pipeline_id: Optional[UUID] = None
    stage_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    value: Optional[int] = None
    currency: Optional[str] = None
    owner_id: Optional[UUID] = None
    expected_close_date: Optional[datetime] = None
    probability: Optional[int] = Field(None, ge=0, le=100)
    source: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None


class DealResponse(DealBase, TimestampMixin):
    id: UUID
    actual_close_date: Optional[datetime] = None
    weighted_value: int = 0
    created_by_id: Optional[UUID] = None
    updated_by_id: Optional[UUID] = None
    owner: Optional[UserResponse] = None
    contact: Optional[ContactResponse] = None
    company: Optional[CompanyResponse] = None
    stage: Optional[StageResponse] = None
    pipeline: Optional[PipelineResponse] = None


class TaskBase(BaseSchema):
    lead_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    status: str = "pending"
    priority: str = "medium"
    owner_id: Optional[UUID] = None
    due_date: Optional[datetime] = None
    reminder_at: Optional[datetime] = None
    is_recurring: bool = False
    recurrence_rule: Optional[str] = None
    custom_fields: Dict[str, Any] = {}


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    lead_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    owner_id: Optional[UUID] = None
    due_date: Optional[datetime] = None
    reminder_at: Optional[datetime] = None
    is_recurring: Optional[bool] = None
    recurrence_rule: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None


class TaskResponse(TaskBase, TimestampMixin):
    id: UUID
    completed_at: Optional[datetime] = None
    reminder_sent: bool = False
    created_by_id: Optional[UUID] = None
    owner: Optional[UserResponse] = None
    lead: Optional[LeadResponse] = None
    deal: Optional[DealResponse] = None


class NoteBase(BaseSchema):
    lead_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    content: str = Field(min_length=1)
    is_pinned: bool = False
    custom_fields: Dict[str, Any] = {}


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1)
    is_pinned: Optional[bool] = None
    custom_fields: Optional[Dict[str, Any]] = None


class NoteResponse(NoteBase, TimestampMixin):
    id: UUID
    author_id: UUID
    author: Optional[UserResponse] = None


class ActivityBase(BaseSchema):
    lead_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    type: str
    subject: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    user_id: Optional[UUID] = None
    metadata: Dict[str, Any] = {}
    is_ai_generated: bool = False
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    correlation_id: Optional[str] = None


class ActivityResponse(ActivityBase, TimestampMixin):
    id: UUID
    user: Optional[UserResponse] = None


class ProposalBase(BaseSchema):
    deal_id: UUID
    title: str = Field(min_length=1, max_length=255)
    version: int = 1
    status: str = "draft"
    executive_summary: Optional[str] = None
    solution_overview: Optional[str] = None
    pricing_details: Optional[Dict[str, Any]] = None
    terms: Optional[str] = None
    expires_at: Optional[datetime] = None


class ProposalCreate(ProposalBase):
    pass


class ProposalUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    version: Optional[int] = None
    status: Optional[str] = None
    executive_summary: Optional[str] = None
    solution_overview: Optional[str] = None
    pricing_details: Optional[Dict[str, Any]] = None
    terms: Optional[str] = None
    expires_at: Optional[datetime] = None
    pdf_url: Optional[str] = None


class ProposalResponse(ProposalBase, TimestampMixin):
    id: UUID
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    is_ai_generated: bool = False
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    created_by_id: UUID
    created_by: Optional[UserResponse] = None


# =============================================================================
# Firecrawl Lead Search Schemas
# =============================================================================

class FirecrawlSearchRequest(BaseModel):
    """Request to search for leads via Firecrawl."""
    query: str = Field(..., min_length=3, max_length=500, description="Search query for finding leads")
    limit: int = Field(10, ge=1, le=50, description="Maximum number of results")
    location: Optional[str] = Field(None, max_length=200, description="Geographic location filter")
    industry: Optional[str] = Field(None, max_length=100, description="Industry filter")
    company_size: Optional[str] = Field(None, max_length=50, description="Company size filter")
    technologies: Optional[List[str]] = Field(None, description="Technology stack filters")


class FirecrawlSearchResult(BaseModel):
    """Single lead result from Firecrawl search."""
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    title: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    phone: Optional[str] = None
    source: str
    medium: str
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    raw_data: Dict[str, Any] = {}
    custom_fields: Dict[str, Any] = {}


class FirecrawlSearchResponse(BaseModel):
    """Response from Firecrawl lead search."""
    success: bool
    query: str
    results_count: int
    leads: List[FirecrawlSearchResult]
    error_message: Optional[str] = None


# =============================================================================
# Lead Approval Workflow Schemas
# =============================================================================

class LeadApprovalStatusEnum(str, Enum):
    """Lead approval status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class LeadSourceApprovalRequest(BaseModel):
    """Request to approve/reject a lead from external source."""
    source: str = Field(..., description="Source of the lead (firecrawl, meta, linkedin, etc.)")
    source_id: str = Field(..., description="External ID from source system")
    lead_data: Dict[str, Any] = Field(..., description="Raw lead data from source")
    action: str = Field(..., description="Action: approve, reject, needs_review")
    reviewer_notes: Optional[str] = None


class LeadSourceApprovalResponse(BaseModel):
    """Response after lead approval action."""
    success: bool
    lead_id: Optional[UUID] = None
    status: LeadApprovalStatusEnum
    message: str
    requires_contact_creation: bool = False


class PendingLeadReview(BaseModel):
    """Lead pending review from external source."""
    id: UUID
    source: str
    source_id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    title: Optional[str] = None
    company_name: Optional[str] = None
    raw_data: Dict[str, Any] = {}
    created_at: datetime
    assigned_reviewer_id: Optional[UUID] = None


class BulkLeadApprovalRequest(BaseModel):
    """Bulk approve/reject multiple leads."""
    lead_ids: List[UUID]
    action: str = Field(..., description="Action: approve, reject")
    reviewer_notes: Optional[str] = None


class BulkLeadApprovalResponse(BaseModel):
    """Response for bulk lead approval."""
    success: bool
    processed: int
    approved: int
    rejected: int
    failed: int
    errors: List[Dict[str, Any]] = []


# Forward references for circular dependencies
ProposalResponse.model_rebuild()