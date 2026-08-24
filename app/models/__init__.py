"""
SQLAlchemy models for Globexa CRM - Multi-tenant core.
All models include tenant_id for isolation.
"""
import enum
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    Enum,
    Index,
    UniqueConstraint,
    Boolean,
    Integer,
    BigInteger,
    JSON,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, declared_attr

from app.core.database import Base


class RoleEnum(str, enum.Enum):
    """System roles per blueprint."""
    OWNER = "owner"
    ADMIN = "admin"
    SALES_MANAGER = "sales_manager"
    SALES_EXECUTIVE = "sales_executive"
    MARKETING = "marketing"
    VIEWER = "viewer"


class PackageEnum(str, enum.Enum):
    """Subscription packages per blueprint."""
    STARTER = "starter"
    GROWTH = "growth"
    AI_PRO = "ai_pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatusEnum(str, enum.Enum):
    """Subscription status."""
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    PAUSED = "paused"
    INCOMPLETE = "incomplete"


class Tenant(Base):
    """Top-level tenant - each business/customer."""
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    domain: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    users: Mapped[List["User"]] = relationship("User", back_populates="tenants", secondary="memberships")
    memberships: Mapped[List["Membership"]] = relationship("Membership", back_populates="tenant", cascade="all, delete-orphan")
    subscription: Mapped[Optional["Subscription"]] = relationship("Subscription", back_populates="tenant", uselist=False, cascade="all, delete-orphan")
    feature_entitlements: Mapped[List["FeatureEntitlement"]] = relationship("FeatureEntitlement", back_populates="tenant", cascade="all, delete-orphan")
    usage_records: Mapped[List["UsageRecord"]] = relationship("UsageRecord", back_populates="tenant", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="tenant", cascade="all, delete-orphan")


class User(Base):
    """User account - can belong to multiple tenants via memberships."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    locale: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    google_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenants: Mapped[List["Tenant"]] = relationship("User", back_populates="users", secondary="memberships")
    memberships: Mapped[List["Membership"]] = relationship("Membership", back_populates="user", cascade="all, delete-orphan")
    owned_tenants: Mapped[List["Tenant"]] = relationship("Tenant", foreign_keys="Tenant.id", backref="owner")


class Membership(Base):
    """User-Tenant membership with role."""
    __tablename__ = "memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), default=RoleEnum.SALES_EXECUTIVE, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invited_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="memberships", foreign_keys=[user_id])
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="memberships")
    invited_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[invited_by_id])

    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_membership_user_tenant"),
        Index("ix_membership_tenant_user", "tenant_id", "user_id"),
    )


class Subscription(Base):
    """Tenant subscription/billing."""
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False)
    package: Mapped[PackageEnum] = mapped_column(Enum(PackageEnum), default=PackageEnum.STARTER, nullable=False)
    status: Mapped[SubscriptionStatusEnum] = mapped_column(Enum(SubscriptionStatusEnum), default=SubscriptionStatusEnum.TRIALING, nullable=False)
    billing_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    current_period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="subscription")


class FeatureEntitlement(Base):
    """Feature flags and limits per tenant (not hard-coded per package)."""
    __tablename__ = "feature_entitlements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    feature_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    limit_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # -1 = unlimited
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="feature_entitlements")

    __table_args__ = (
        UniqueConstraint("tenant_id", "feature_key", name="uq_feature_entitlement_tenant_feature"),
    )


class UsageRecord(Base):
    """Usage metering for billing/limits."""
    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    metric: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # emails_sent, ai_credits, contacts, etc.
    quantity: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="usage_records")
    user: Mapped[Optional["User"]] = relationship("User")

    __table_args__ = (
        Index("ix_usage_tenant_metric_period", "tenant_id", "metric", "period_start"),
    )


class AuditLog(Base):
    """Immutable audit trail for security/compliance."""
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    old_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="audit_logs")
    user: Mapped[Optional["User"]] = relationship("User")

    __table_args__ = (
        Index("ix_audit_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_user_created", "user_id", "created_at"),
    )


# =============================================================================
# AI-related models (for AI Router usage ledger)
# =============================================================================

class AIProviderEnum(str, enum.Enum):
    """AI provider types."""
    OLLAMA = "ollama"
    NVIDIA = "nvidia"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


class AITaskTypeEnum(str, enum.Enum):
    """AI task types per blueprint."""
    CLASSIFICATION = "classification"
    SIMPLE_SCORING = "simple_scoring"
    EXTRACTION = "extraction"
    SUMMARIZATION = "summarization"
    INTENT_IDENTIFICATION = "intent_identification"
    TAGGING = "tagging"
    ROUTING_DECISION = "routing_decision"
    LEAD_SCORING = "lead_scoring"
    PERSONALIZATION = "personalization"
    CAMPAIGN_GENERATION = "campaign_generation"
    PROPOSAL_GENERATION = "proposal_generation"
    REPLY_ANALYSIS = "reply_analysis"
    REPLY_GENERATION = "reply_generation"
    NEXT_BEST_ACTION = "next_best_action"
    LEAD_MINING = "lead_mining"
    RESEARCH = "research"
    CHAT_ASSISTANT = "chat_assistant"


class AIUsageLog(Base):
    """AI invocation ledger per blueprint - every AI request recorded."""
    __tablename__ = "ai_usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    task_type: Mapped[AITaskTypeEnum] = mapped_column(Enum(AITaskTypeEnum), nullable=False, index=True)
    provider: Mapped[AIProviderEnum] = mapped_column(Enum(AIProviderEnum), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[Optional[float]] = mapped_column(nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_actions: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    user: Mapped[Optional["User"]] = relationship("User")

    __table_args__ = (
        Index("ix_ai_usage_tenant_created", "tenant_id", "created_at"),
        Index("ix_ai_usage_tenant_task_created", "tenant_id", "task_type", "created_at"),
    )


# =============================================================================
# CRM Models (Phase 2)
# =============================================================================

class LeadSourceEnum(str, enum.Enum):
    """Lead source types per blueprint."""
    WEBSITE = "website"
    META_LEAD_ADS = "meta_lead_ads"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    GOOGLE_ADS = "google_ads"
    CSV_IMPORT = "csv_import"
    WHATSAPP = "whatsapp"
    EMAIL_INBOX = "email_inbox"
    APOLLO = "apollo"
    WEBSITE_CHATBOT = "website_chatbot"
    AI_LEAD_MINER = "ai_lead_miner"
    REFERRAL = "referral"
    MANUAL = "manual"
    API = "api"
    WEBHOOK = "webhook"
    APPOINTMENTS = "appointments"
    PARTNER_INTEGRATION = "partner_integration"
    OTHER = "other"


class LeadStatusEnum(str, enum.Enum):
    """Lead status per blueprint pipeline."""
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    UNQUALIFIED = "unqualified"
    NURTURING = "nurturing"
    CONVERTED = "converted"
    LOST = "lost"


class DealStageEnum(str, enum.Enum):
    """Deal pipeline stages."""
    PROSPECTING = "prospecting"
    QUALIFICATION = "qualification"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class TaskStatusEnum(str, enum.Enum):
    """Task status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriorityEnum(str, enum.Enum):
    """Task priority."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ActivityTypeEnum(str, enum.Enum):
    """Activity types for timeline."""
    NOTE = "note"
    CALL = "call"
    EMAIL = "email"
    MEETING = "meeting"
    TASK = "task"
    EMAIL_OPENED = "email_opened"
    EMAIL_CLICKED = "email_clicked"
    EMAIL_REPLIED = "email_replied"
    EMAIL_BOUNCED = "email_bounced"
    STAGE_CHANGED = "stage_changed"
    ASSIGNMENT = "assignment"
    AI_ACTION = "ai_action"
    CAMPAIGN_SENT = "campaign_sent"
    WHATSAPP_SENT = "whatsapp_sent"
    WHATSAPP_RECEIVED = "whatsapp_received"


class Company(Base):
    """Company/Account model."""
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # e.g., "1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"
    annual_revenue: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    facebook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    twitter_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Attribution
    source: Mapped[Optional[LeadSourceEnum]] = mapped_column(Enum(LeadSourceEnum), nullable=True)
    utm_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_content: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_term: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # AI fields
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_icp_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ai_icp_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    contacts: Mapped[List["Contact"]] = relationship("Contact", back_populates="company", cascade="all, delete-orphan")
    deals: Mapped[List["Deal"]] = relationship("Deal", back_populates="company")
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])
    updated_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[updated_by_id])

    __table_args__ = (
        Index("ix_companies_tenant_name", "tenant_id", "name"),
        Index("ix_companies_tenant_domain", "tenant_id", "domain"),
        Index("ix_companies_tenant_source", "tenant_id", "source"),
    )


class Contact(Base):
    """Contact model."""
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    mobile: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Address
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Status
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_opted_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sms_opted_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Attribution
    source: Mapped[Optional[LeadSourceEnum]] = mapped_column(Enum(LeadSourceEnum), nullable=True)
    utm_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_content: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_term: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # AI fields
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_lead_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    company: Mapped[Optional["Company"]] = relationship("Company", back_populates="contacts")
    leads: Mapped[List["Lead"]] = relationship("Lead", back_populates="contact")
    deals: Mapped[List["Deal"]] = relationship("Deal", back_populates="contact")
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])
    updated_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[updated_by_id])

    __table_args__ = (
        Index("ix_contacts_tenant_email", "tenant_id", "email"),
        Index("ix_contacts_tenant_company", "tenant_id", "company_id"),
        Index("ix_contacts_tenant_name", "tenant_id", "last_name", "first_name"),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Lead(Base):
    """Lead model - the core sales object."""
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    # Lead identification
    title: Mapped[str] = mapped_column(String(255), nullable=False)  # Lead title/subject
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Status & qualification
    status: Mapped[LeadStatusEnum] = mapped_column(Enum(LeadStatusEnum), default=LeadStatusEnum.NEW, nullable=False, index=True)
    # Assignment
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Source & attribution
    source: Mapped[Optional[LeadSourceEnum]] = mapped_column(Enum(LeadSourceEnum), nullable=True, index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # External ID from source
    utm_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_content: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_term: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    referrer_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    landing_page: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # AI fields
    ai_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)  # 0-100
    ai_score_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_next_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_next_action_confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Qualification
    is_qualified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    qualified_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    qualified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    qualification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Conversion
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_deal_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="SET NULL"), nullable=True)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    contact: Mapped[Optional["Contact"]] = relationship("Contact", back_populates="leads")
    company: Mapped[Optional["Company"]] = relationship("Company", backref="leads")
    owner: Mapped[Optional["User"]] = relationship("User", foreign_keys=[owner_id], backref="owned_leads")
    assigned_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_by_id])
    qualified_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[qualified_by_id])
    activities: Mapped[List["Activity"]] = relationship("Activity", back_populates="lead", cascade="all, delete-orphan")
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="lead", cascade="all, delete-orphan")
    notes: Mapped[List["Note"]] = relationship("Note", back_populates="lead", cascade="all, delete-orphan")
    converted_deal: Mapped[Optional["Deal"]] = relationship("Deal", foreign_keys=[converted_deal_id])

    __table_args__ = (
        Index("ix_leads_tenant_status", "tenant_id", "status"),
        Index("ix_leads_tenant_owner", "tenant_id", "owner_id"),
        Index("ix_leads_tenant_source", "tenant_id", "source"),
        Index("ix_leads_tenant_ai_score", "tenant_id", "ai_score"),
        Index("ix_leads_tenant_created", "tenant_id", "created_at"),
    )


class Pipeline(Base):
    """Sales pipeline model."""
    __tablename__ = "pipelines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    stages: Mapped[List["Stage"]] = relationship("Stage", back_populates="pipeline", cascade="all, delete-orphan", order_by="Stage.order")
    deals: Mapped[List["Deal"]] = relationship("Deal", back_populates="pipeline")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_pipeline_tenant_name"),
    )


class Stage(Base):
    """Pipeline stage model."""
    __tablename__ = "stages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    probability: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0-100
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_won: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # Hex color
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    pipeline: Mapped["Pipeline"] = relationship("Pipeline", back_populates="stages")
    deals: Mapped[List["Deal"]] = relationship("Deal", back_populates="stage")

    __table_args__ = (
        UniqueConstraint("pipeline_id", "order", name="uq_stage_pipeline_order"),
        UniqueConstraint("pipeline_id", "name", name="uq_stage_pipeline_name"),
    )


class Deal(Base):
    """Deal/Opportunity model."""
    __tablename__ = "deals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    # Core relations
    pipeline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stages.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    # Deal details
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)  # In cents
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    # Assignment
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # Dates
    expected_close_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_close_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Probability & forecasting
    probability: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0-100
    weighted_value: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)  # value * probability / 100
    # Source
    source: Mapped[Optional[LeadSourceEnum]] = mapped_column(Enum(LeadSourceEnum), nullable=True)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    pipeline: Mapped["Pipeline"] = relationship("Pipeline", back_populates="deals")
    stage: Mapped["Stage"] = relationship("Stage", back_populates="deals")
    contact: Mapped[Optional["Contact"]] = relationship("Contact", back_populates="deals")
    company: Mapped[Optional["Company"]] = relationship("Company", back_populates="deals")
    lead: Mapped[Optional["Lead"]] = relationship("Lead", foreign_keys=[lead_id])
    owner: Mapped[Optional["User"]] = relationship("User", foreign_keys=[owner_id], backref="owned_deals")
    activities: Mapped[List["Activity"]] = relationship("Activity", back_populates="deal", cascade="all, delete-orphan")
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="deal", cascade="all, delete-orphan")
    notes: Mapped[List["Note"]] = relationship("Note", back_populates="deal", cascade="all, delete-orphan")
    proposals: Mapped[List["Proposal"]] = relationship("Proposal", back_populates="deal", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_deals_tenant_stage", "tenant_id", "stage_id"),
        Index("ix_deals_tenant_owner", "tenant_id", "owner_id"),
        Index("ix_deals_tenant_pipeline", "tenant_id", "pipeline_id"),
        Index("ix_deals_tenant_expected_close", "tenant_id", "expected_close_date"),
    )


class Task(Base):
    """Task/Activity model."""
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    # Relations
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True)
    deal_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=True, index=True)
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True)
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    # Task details
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatusEnum] = mapped_column(Enum(TaskStatusEnum), default=TaskStatusEnum.PENDING, nullable=False, index=True)
    priority: Mapped[TaskPriorityEnum] = mapped_column(Enum(TaskPriorityEnum), default=TaskPriorityEnum.MEDIUM, nullable=False)
    # Assignment
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Dates
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Reminders
    reminder_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Recurrence
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurrence_rule: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # RRULE format
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    lead: Mapped[Optional["Lead"]] = relationship("Lead", back_populates="tasks")
    deal: Mapped[Optional["Deal"]] = relationship("Deal", back_populates="tasks")
    contact: Mapped[Optional["Contact"]] = relationship("Contact", backref="tasks")
    company: Mapped[Optional["Company"]] = relationship("Company", backref="tasks")
    owner: Mapped[Optional["User"]] = relationship("User", foreign_keys=[owner_id], backref="assigned_tasks")
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_tasks_tenant_owner_status", "tenant_id", "owner_id", "status"),
        Index("ix_tasks_tenant_due_date", "tenant_id", "due_date"),
        Index("ix_tasks_tenant_lead", "tenant_id", "lead_id"),
        Index("ix_tasks_tenant_deal", "tenant_id", "deal_id"),
    )


class Note(Base):
    """Note model for leads, deals, contacts, companies."""
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    # Polymorphic relations (one of these will be set)
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True)
    deal_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=True, index=True)
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True)
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    # Note content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Author
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    lead: Mapped[Optional["Lead"]] = relationship("Lead", back_populates="notes")
    deal: Mapped[Optional["Deal"]] = relationship("Deal", back_populates="notes")
    contact: Mapped[Optional["Contact"]] = relationship("Contact", backref="notes")
    company: Mapped[Optional["Company"]] = relationship("Company", backref="notes")
    author: Mapped["User"] = relationship("User", foreign_keys=[author_id])

    __table_args__ = (
        Index("ix_notes_tenant_lead", "tenant_id", "lead_id"),
        Index("ix_notes_tenant_deal", "tenant_id", "deal_id"),
        Index("ix_notes_tenant_contact", "tenant_id", "contact_id"),
        Index("ix_notes_tenant_company", "tenant_id", "company_id"),
    )


class Activity(Base):
    """Activity/Timeline model for complete audit trail."""
    __tablename__ = "activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    # Polymorphic relations
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True)
    deal_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=True, index=True)
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True)
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    # Activity details
    type: Mapped[ActivityTypeEnum] = mapped_column(Enum(ActivityTypeEnum), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Actor
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # Metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    # AI attribution
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ai_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    lead: Mapped[Optional["Lead"]] = relationship("Lead", back_populates="activities")
    deal: Mapped[Optional["Deal"]] = relationship("Deal", back_populates="activities")
    contact: Mapped[Optional["Contact"]] = relationship("Contact", backref="activities")
    company: Mapped[Optional["Company"]] = relationship("Company", backref="activities")
    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("ix_activities_tenant_lead_created", "tenant_id", "lead_id", "created_at"),
        Index("ix_activities_tenant_deal_created", "tenant_id", "deal_id", "created_at"),
        Index("ix_activities_tenant_type_created", "tenant_id", "type", "created_at"),
        Index("ix_activities_tenant_user_created", "tenant_id", "user_id", "created_at"),
    )


class Proposal(Base):
    """Proposal model per blueprint."""
    __tablename__ = "proposals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True)
    # Proposal details
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)  # draft, sent, viewed, accepted, rejected, expired, superseded
    # Content
    executive_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    solution_overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pricing_details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # Structured pricing
    terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Files
    pdf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Tracking
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # AI
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ai_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Author
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    deal: Mapped["Deal"] = relationship("Deal", back_populates="proposals")
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_proposals_tenant_deal", "tenant_id", "deal_id"),
        Index("ix_proposals_tenant_status", "tenant_id", "status"),
    )


class ProposalTemplate(Base):
    """Proposal template model for reusable proposal structures."""
    __tablename__ = "proposal_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # Template structure with placeholders
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_proposal_template_tenant_name"),
    )


class Product(Base):
    """Product/Service catalog model."""
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    price_cents: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    billing_type: Mapped[str] = mapped_column(String(50), default="one_time", nullable=False)  # one_time, recurring, usage
    billing_period: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # monthly, yearly, etc.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_products_tenant_name", "tenant_id", "name"),
        Index("ix_products_tenant_sku", "tenant_id", "sku"),
    )


# =============================================================================
# Campaign & Email Models (Phase 3)
# =============================================================================

class CampaignTypeEnum(str, enum.Enum):
    """Campaign types per blueprint."""
    BROADCAST = "broadcast"
    SEQUENCE = "sequence"
    TRIGGERED = "triggered"


class CampaignStatusEnum(str, enum.Enum):
    """Campaign status."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CampaignRecipientStatusEnum(str, enum.Enum):
    """Campaign recipient lifecycle per blueprint."""
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    REPLIED = "replied"
    BOUNCED = "bounced"
    COMPLAINED = "complained"
    UNSUBSCRIBED = "unsubscribed"
    SUPPRESSED = "suppressed"
    FAILED = "failed"


class AudienceTypeEnum(str, enum.Enum):
    """Audience types."""
    STATIC = "static"      # Fixed list of contacts
    DYNAMIC = "dynamic"    # Criteria-based (segment)


class TriggerTypeEnum(str, enum.Enum):
    """Trigger types for triggered campaigns."""
    EMAIL_OPENED = "email_opened"
    EMAIL_CLICKED = "email_clicked"
    EMAIL_REPLIED = "email_replied"
    LINK_CLICKED = "link_clicked"
    FORM_SUBMITTED = "form_submitted"
    STAGE_CHANGED = "stage_changed"
    DEAL_CREATED = "deal_created"
    TASK_COMPLETED = "task_completed"
    CUSTOM_EVENT = "custom_event"
    DATE_BASED = "date_based"


class EmailProviderTypeEnum(str, enum.Enum):
    """Email provider types."""
    RESEND = "resend"
    GMAIL = "gmail"
    MICROSOFT = "microsoft"
    SMTP = "smtp"


class Campaign(Base):
    """Campaign model per blueprint."""
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[CampaignTypeEnum] = mapped_column(Enum(CampaignTypeEnum), nullable=False, index=True)
    status: Mapped[CampaignStatusEnum] = mapped_column(Enum(CampaignStatusEnum), default=CampaignStatusEnum.DRAFT, nullable=False, index=True)
    # Sending identity
    sending_domain_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("sending_domains.id", ondelete="SET NULL"), nullable=True)
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    reply_to_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Scheduling
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # AI Personalization
    ai_personalization_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_personalization_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Settings
    track_opens: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    track_clicks: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    unsubscribe_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Metadata
    tags: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    audience: Mapped[Optional["CampaignAudience"]] = relationship("CampaignAudience", back_populates="campaign", uselist=False, cascade="all, delete-orphan")
    templates: Mapped[List["CampaignTemplate"]] = relationship("CampaignTemplate", back_populates="campaign", cascade="all, delete-orphan", order_by="CampaignTemplate.step_order")
    recipients: Mapped[List["CampaignRecipient"]] = relationship("CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan")
    sequences: Mapped[List["CampaignSequence"]] = relationship("CampaignSequence", back_populates="campaign", cascade="all, delete-orphan")
    triggers: Mapped[List["CampaignTrigger"]] = relationship("CampaignTrigger", back_populates="campaign", cascade="all, delete-orphan")
    stats: Mapped[Optional["CampaignStats"]] = relationship("CampaignStats", back_populates="campaign", uselist=False, cascade="all, delete-orphan")
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])
    updated_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[updated_by_id])

    __table_args__ = (
        Index("ix_campaigns_tenant_status", "tenant_id", "status"),
        Index("ix_campaigns_tenant_type", "tenant_id", "type"),
        Index("ix_campaigns_tenant_scheduled", "tenant_id", "scheduled_at"),
    )


class CampaignAudience(Base):
    """Campaign audience/segment."""
    __tablename__ = "campaign_audiences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), unique=True, nullable=False)
    # Audience definition
    type: Mapped[AudienceTypeEnum] = mapped_column(Enum(AudienceTypeEnum), default=AudienceTypeEnum.STATIC, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Static audience - list of contact IDs
    contact_ids: Mapped[List[uuid.UUID]] = mapped_column(JSONB, default=list, nullable=False)
    # Dynamic audience - filter criteria
    filters: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # e.g., {"status": ["qualified"], "tags": ["vip"], "custom_field": "value"}
    # Exclusion
    exclude_contact_ids: Mapped[List[uuid.UUID]] = mapped_column(JSONB, default=list, nullable=False)
    exclude_suppressed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    exclude_unsubscribed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    exclude_bounced: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Computed
    estimated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="audience")


class CampaignTemplate(Base):
    """Email template for campaigns (versioned per blueprint)."""
    __tablename__ = "campaign_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    # Template details
    step_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # For sequences
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    preheader: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    html_content: Mapped[str] = mapped_column(Text, nullable=False)
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # AI Personalization
    ai_personalization_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_personalization_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Versioning (per blueprint: content versioned so edits don't alter historical sends)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active_version: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="templates")

    __table_args__ = (
        UniqueConstraint("campaign_id", "step_order", name="uq_template_campaign_step"),
    )


class CampaignRecipient(Base):
    """Individual recipient tracking per blueprint email-event model."""
    __tablename__ = "campaign_recipients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("campaign_templates.id", ondelete="SET NULL"), nullable=True)
    # Recipient
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)  # Denormalized for sending
    # Status per blueprint
    status: Mapped[CampaignRecipientStatusEnum] = mapped_column(Enum(CampaignRecipientStatusEnum), default=CampaignRecipientStatusEnum.QUEUED, nullable=False, index=True)
    # Provider tracking
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    provider_type: Mapped[Optional[EmailProviderTypeEnum]] = mapped_column(Enum(EmailProviderTypeEnum), nullable=True)
    # Timestamps
    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    first_opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    first_clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    bounced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    complained_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    unsubscribed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Engagement counts
    open_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Bounce details
    bounce_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # hard, soft
    bounce_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Error
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Idempotency
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    # AI
    ai_personalized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_personalization_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="recipients")
    template: Mapped[Optional["CampaignTemplate"]] = relationship("CampaignTemplate")
    contact: Mapped["Contact"] = relationship("Contact")

    __table_args__ = (
        Index("ix_campaign_recipients_campaign_status", "campaign_id", "status"),
        Index("ix_campaign_recipients_tenant_contact", "tenant_id", "contact_id"),
        Index("ix_campaign_recipients_provider_msg", "provider_message_id"),
        Index("ix_campaign_recipients_idempotency", "idempotency_key"),
    )


class CampaignSequence(Base):
    """Multi-step sequence for sequence campaigns."""
    __tablename__ = "campaign_sequences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    # Sequence step
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaign_templates.id", ondelete="CASCADE"), nullable=False)
    # Timing
    delay_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Days after previous step
    delay_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    send_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)  # HH:MM in tenant timezone
    send_timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    # Conditions
    send_on_weekends: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stop_on_reply: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    stop_on_unsubscribe: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    stop_on_bounce: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="sequences")
    template: Mapped["CampaignTemplate"] = relationship("CampaignTemplate")

    __table_args__ = (
        UniqueConstraint("campaign_id", "step_order", name="uq_sequence_campaign_step"),
    )


class CampaignTrigger(Base):
    """Triggered campaign rules per blueprint."""
    __tablename__ = "campaign_triggers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    # Trigger definition
    trigger_type: Mapped[TriggerTypeEnum] = mapped_column(Enum(TriggerTypeEnum), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Conditions (JSON logic)
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # e.g., {"link_url": "pricing", "score_gt": 50}
    # Action
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaign_templates.id", ondelete="CASCADE"), nullable=False)
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Limits
    max_triggers_per_contact: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cooldown_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="triggers")
    template: Mapped["CampaignTemplate"] = relationship("CampaignTemplate")


class CampaignStats(Base):
    """Campaign analytics per blueprint metrics."""
    __tablename__ = "campaign_stats"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), unique=True, nullable=False)
    # Delivery metrics
    total_recipients: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queued: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bounced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    suppressed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Engagement metrics
    opened: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    replied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unsubscribed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    complained: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Sales metrics
    interested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qualified_leads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    appointments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proposals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revenue: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)  # In cents
    # AI metrics
    ai_personalized_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_cost_usd: Mapped[float] = mapped_column(default=0.0, nullable=False)
    ai_reply_classifications: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Rates (computed)
    delivery_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    open_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    click_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    reply_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    bounce_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    unsubscribe_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    conversion_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    # Attribution
    attribution_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Timestamps
    last_calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="stats")


# Email Events (per blueprint email-event model)
class EmailEvent(Base):
    """Raw email events from providers for audit/reconciliation."""
    __tablename__ = "email_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    # Provider info
    provider: Mapped[EmailProviderTypeEnum] = mapped_column(Enum(EmailProviderTypeEnum), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider_event_type: Mapped[str] = mapped_column(String(100), nullable=False)  # delivered, opened, clicked, bounced, etc.
    # Link to our recipient
    recipient_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("campaign_recipients.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    # Event data
    event_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # Timestamps
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Processing
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_email_event_provider_event"),
        Index("ix_email_events_tenant_recipient", "tenant_id", "recipient_id"),
        Index("ix_email_events_tenant_timestamp", "tenant_id", "event_timestamp"),
    )


class SuppressionList(Base):
    """Suppression list per blueprint (tenant + sending identity level)."""
    __tablename__ = "suppression_lists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    sending_domain_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("sending_domains.id", ondelete="CASCADE"), nullable=True)
    # Suppressed contact
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    # Reason
    reason: Mapped[str] = mapped_column(String(100), nullable=False)  # bounced, complained, unsubscribed, manual, spam
    reason_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Source
    provider: Mapped[Optional[EmailProviderTypeEnum]] = mapped_column(Enum(EmailProviderTypeEnum), nullable=True)
    provider_event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # For temporary suppressions
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", "sending_domain_id", name="uq_suppression_tenant_email_domain"),
        Index("ix_suppression_lists_tenant_active", "tenant_id", "is_active"),
    )


class SendingDomain(Base):
    """Sending domain per blueprint cold outreach strategy."""
    __tablename__ = "sending_domains"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    # Domain info
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subdomain: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # e.g., "outbound" for outbound.example.com
    from_name: Mapped[str] = mapped_column(String(255), nullable=False)
    from_email: Mapped[str] = mapped_column(String(255), nullable=False)
    reply_to_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Provider config
    provider: Mapped[EmailProviderTypeEnum] = mapped_column(Enum(EmailProviderTypeEnum), nullable=False)
    provider_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # Encrypted credentials
    # Verification
    dkim_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    spf_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dmarc_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Warmup & limits per blueprint
    warmup_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    warmup_stage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0=not started, 1-4=stages
    daily_limit: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    current_daily_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_sent_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Health metrics
    bounce_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    complaint_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    reply_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    health_score: Mapped[int] = mapped_column(Integer, default=100, nullable=False)  # 0-100
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pause_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "domain", "subdomain", name="uq_sending_domain_tenant_domain_sub"),
        Index("ix_sending_domains_tenant_active", "tenant_id", "is_active"),
    )


class EmailProviderConfig(Base):
    """Tenant-scoped email provider credentials (encrypted)."""
    __tablename__ = "email_provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[EmailProviderTypeEnum] = mapped_column(Enum(EmailProviderTypeEnum), nullable=False)
    # Encrypted credentials (application-level encryption)
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # JSON encrypted
    # Config
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # User-friendly name
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", "name", name="uq_email_config_tenant_provider_name"),
        Index("ix_email_configs_tenant_default", "tenant_id", "is_default"),
    )


# =============================================================================
# Integration Framework Models (Phase 4)
# =============================================================================

class IntegrationTypeEnum(str, enum.Enum):
    """Integration types per blueprint lead sources."""
    META = "meta"                    # Facebook/Instagram Lead Ads
    GOOGLE_ADS = "google_ads"        # Google Ads
    LINKEDIN = "linkedin"            # LinkedIn Lead Gen Forms
    APOLLO = "apollo"                # Apollo.io
    WHATSAPP = "whatsapp"            # WhatsApp Business API
    CSV = "csv"                      # CSV/Excel import
    WEBHOOK = "webhook"              # Generic webhook
    EMAIL_INBOX = "email_inbox"      # Email inbox parsing
    WEBSITE_FORM = "website_form"    # Website form submissions
    WEBSITE_CHATBOT = "website_chatbot"  # Website chatbot
    AI_LEAD_MINER = "ai_lead_miner"  # AI Lead Miner
    APPOINTMENTS = "appointments"    # Appointment booking
    REFERRAL = "referral"            # Referral tracking
    PARTNER = "partner"              # Partner integrations
    API = "api"                      # Custom API
    OTHER = "other"                  # Other/custom


class IntegrationStatusEnum(str, enum.Enum):
    """Integration connection status."""
    PENDING = "pending"
    CONNECTED = "connected"
    ERROR = "error"
    DISCONNECTED = "disconnected"
    EXPIRED = "expired"              # Token expired


class SyncStatusEnum(str, enum.Enum):
    """Sync job status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class FieldMappingTypeEnum(str, enum.Enum):
    """Field mapping types."""
    DIRECT = "direct"                # Direct field mapping
    TRANSFORM = "transform"          # Transform function
    STATIC = "static"                # Static value
    COMPUTED = "computed"            # Computed from multiple fields


class AttributionModelEnum(str, enum.Enum):
    """Attribution models."""
    FIRST_TOUCH = "first_touch"
    LAST_TOUCH = "last_touch"
    LINEAR = "linear"
    TIME_DECAY = "time_decay"
    U_SHAPED = "u_shaped"
    W_SHAPED = "w_shaped"
    CUSTOM = "custom"


class Integration(Base):
    """Integration/Connection configuration per tenant."""
    __tablename__ = "integrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    # Integration details
    type: Mapped[IntegrationTypeEnum] = mapped_column(Enum(IntegrationTypeEnum), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Status
    status: Mapped[IntegrationStatusEnum] = mapped_column(Enum(IntegrationStatusEnum), default=IntegrationStatusEnum.PENDING, nullable=False, index=True)
    # Configuration
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # API endpoints, webhook URLs, etc.
    # Sync settings
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sync_frequency_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)  # 0 = manual only
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[Optional[SyncStatusEnum]] = mapped_column(Enum(SyncStatusEnum), nullable=True)
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    records_synced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Field mapping (source -> CRM field)
    field_mappings: Mapped[List[dict]] = mapped_column(JSONB, default=list, nullable=False)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    credentials: Mapped[List["IntegrationCredential"]] = relationship("IntegrationCredential", back_populates="integration", cascade="all, delete-orphan")
    webhooks: Mapped[List["WebhookEndpoint"]] = relationship("WebhookEndpoint", back_populates="integration", cascade="all, delete-orphan")
    sync_logs: Mapped[List["IntegrationSyncLog"]] = relationship("IntegrationSyncLog", back_populates="integration", cascade="all, delete-orphan")
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])
    updated_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[updated_by_id])

    __table_args__ = (
        UniqueConstraint("tenant_id", "type", "name", name="uq_integration_tenant_type_name"),
        Index("ix_integrations_tenant_type", "tenant_id", "type"),
        Index("ix_integrations_tenant_status", "tenant_id", "status"),
    )


class IntegrationCredential(Base):
    """Encrypted credentials for integrations."""
    __tablename__ = "integration_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    # Credential details
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "access_token", "api_key", "client_secret"
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # Encrypted JSON
    # OAuth fields
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Encrypted
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Encrypted
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    token_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    scopes: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    integration: Mapped["Integration"] = relationship("Integration", back_populates="credentials")

    __table_args__ = (
        UniqueConstraint("integration_id", "name", name="uq_credential_integration_name"),
        Index("ix_credentials_tenant_integration", "tenant_id", "integration_id"),
    )


class WebhookEndpoint(Base):
    """Webhook endpoints for receiving integration events."""
    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("integrations.id", ondelete="CASCADE"), nullable=True, index=True)
    # Endpoint details
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url_path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)  # e.g., "/webhooks/meta/leadgen"
    secret: Mapped[str] = mapped_column(String(255), nullable=False)  # For signature verification
    # Events
    events: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)  # e.g., ["lead.created", "lead.updated"]
    # Processing
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    retry_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Rate limiting
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    # Response
    response_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Custom response
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    integration: Mapped[Optional["Integration"]] = relationship("Integration", back_populates="webhooks")

    __table_args__ = (
        UniqueConstraint("tenant_id", "url_path", name="uq_webhook_tenant_path"),
        Index("ix_webhooks_tenant_active", "tenant_id", "is_active"),
    )


class IntegrationSyncLog(Base):
    """Sync job execution logs."""
    __tablename__ = "integration_sync_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    # Sync details
    sync_type: Mapped[str] = mapped_column(String(50), nullable=False)  # full, incremental, manual
    status: Mapped[SyncStatusEnum] = mapped_column(Enum(SyncStatusEnum), default=SyncStatusEnum.PENDING, nullable=False)
    # Counts
    records_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Error info
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(nullable=True)
    # Trigger
    triggered_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # scheduled, manual, webhook
    triggered_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    integration: Mapped["Integration"] = relationship("Integration", back_populates="sync_logs")
    triggered_by_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[triggered_by_user_id])

    __table_args__ = (
        Index("ix_sync_logs_integration_started", "integration_id", "started_at"),
        Index("ix_sync_logs_tenant_status", "tenant_id", "status"),
    )


# Lead Source Config (per blueprint - configurable sources)
class LeadSourceConfig(Base):
    """Configurable lead sources per tenant."""
    __tablename__ = "lead_source_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    # Source definition
    source_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # e.g., "meta_facebook", "google_ads_brand"
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Type mapping
    source_type: Mapped[IntegrationTypeEnum] = mapped_column(Enum(IntegrationTypeEnum), nullable=False)
    # Attribution defaults
    default_utm_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_utm_medium: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_utm_campaign: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Behavior
    auto_create_contact: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_create_company: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_lead_status: Mapped[str] = mapped_column(String(50), default="new", nullable=False)
    default_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Deduplication
    deduplication_fields: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)  # e.g., ["email", "phone"]
    # Metadata
    icon: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # Hex color
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    default_owner: Mapped[Optional["User"]] = relationship("User", foreign_keys=[default_owner_id])

    __table_args__ = (
        UniqueConstraint("tenant_id", "source_key", name="uq_lead_source_tenant_key"),
        Index("ix_lead_sources_tenant_active", "tenant_id", "is_active"),
    )


# Attribution Models
class Touchpoint(Base):
    """Individual marketing touchpoint per blueprint attribution."""
    __tablename__ = "touchpoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    # Associated records
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    deal_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="SET NULL"), nullable=True, index=True)
    # Touchpoint details
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # google, facebook, linkedin, etc.
    medium: Mapped[str] = mapped_column(String(100), nullable=False)  # cpc, organic, email, referral, etc.
    campaign: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    ad_group: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ad_creative: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    landing_page: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # UTM parameters
    utm_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    utm_content: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_term: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Referrer
    referrer_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Interaction
    interaction_type: Mapped[str] = mapped_column(String(50), nullable=False)  # click, view, form_submit, call, chat
    interaction_value: Mapped[Optional[float]] = mapped_column(nullable=True)  # e.g., time on page, scroll depth
    # Cost
    cost: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # In cents
    # Attribution
    is_first_touch: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_last_touch: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    attribution_weight: Mapped[float] = mapped_column(default=1.0, nullable=False)  # For custom models
    # Source
    integration_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("integrations.id", ondelete="SET NULL"), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Click ID, etc.
    # Timestamps
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    contact: Mapped[Optional["Contact"]] = relationship("Contact")
    lead: Mapped[Optional["Lead"]] = relationship("Lead")
    deal: Mapped[Optional["Deal"]] = relationship("Deal")
    integration: Mapped[Optional["Integration"]] = relationship("Integration")

    __table_args__ = (
        Index("ix_touchpoints_tenant_contact_occurred", "tenant_id", "contact_id", "occurred_at"),
        Index("ix_touchpoints_tenant_lead_occurred", "tenant_id", "lead_id", "occurred_at"),
        Index("ix_touchpoints_tenant_deal_occurred", "tenant_id", "deal_id", "occurred_at"),
        Index("ix_touchpoints_tenant_source_occurred", "tenant_id", "source", "occurred_at"),
        Index("ix_touchpoints_tenant_campaign", "tenant_id", "campaign"),
    )


class AttributionRule(Base):
    """Attribution rules per tenant."""
    __tablename__ = "attribution_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    # Rule definition
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[AttributionModelEnum] = mapped_column(Enum(AttributionModelEnum), default=AttributionModelEnum.LAST_TOUCH, nullable=False)
    # Lookback window
    lookback_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    # Touchpoint filters
    included_sources: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    excluded_sources: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    included_mediums: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    excluded_mediums: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    # Weighting (for custom models)
    first_touch_weight: Mapped[float] = mapped_column(default=0.4, nullable=False)
    last_touch_weight: Mapped[float] = mapped_column(default=0.4, nullable=False)
    middle_touch_weight: Mapped[float] = mapped_column(default=0.2, nullable=False)
    # Time decay (for time_decay model)
    half_life_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_attribution_rule_tenant_name"),
        Index("ix_attribution_rules_tenant_active", "tenant_id", "is_active"),
    )


class RevenueAttribution(Base):
    """Revenue attribution results per deal."""
    __tablename__ = "revenue_attributions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True)
    attribution_rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("attribution_rules.id", ondelete="CASCADE"), nullable=False)
    # Attributed revenue
    attributed_revenue: Mapped[int] = mapped_column(BigInteger, nullable=False)  # In cents
    # Breakdown by touchpoint
    touchpoint_attributions: Mapped[List[dict]] = mapped_column(JSONB, default=list, nullable=False)
    # Summary by source/medium/campaign
    by_source: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    by_medium: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    by_campaign: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # Computed
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    deal: Mapped["Deal"] = relationship("Deal")
    attribution_rule: Mapped["AttributionRule"] = relationship("AttributionRule")

    __table_args__ = (
        UniqueConstraint("deal_id", "attribution_rule_id", name="uq_revenue_attribution_deal_rule"),
        Index("ix_revenue_attributions_tenant_deal", "tenant_id", "deal_id"),
    )


# =============================================================================
# AI Models (Phase 5)
# =============================================================================

class ICPProfile(Base):
    """ICP Profile for AI Lead Miner."""
    __tablename__ = "icp_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    criteria: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    min_score_threshold: Mapped[int] = mapped_column(Integer, default=85, nullable=False)
    # Stats
    prospects_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prospects_qualified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prospects_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Metadata
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_icp_profiles_tenant_active", "tenant_id", "is_active"),
    )