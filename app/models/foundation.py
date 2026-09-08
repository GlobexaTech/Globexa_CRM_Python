"""Checkpoint 2 entities. Global catalogs have no tenant-owned customer data."""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.core.credentials import EncryptedText


class TenantEntity:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthToken(TenantEntity, Base):
    __tablename__ = "oauth_tokens"
    integration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    access_token: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(EncryptedText())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[list] = mapped_column(JSONB, default=list)


class DomainEvent(TenantEntity, Base):
    __tablename__ = "domain_events"
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)


class EventDelivery(TenantEntity, Base):
    __tablename__ = "event_deliveries"
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domain_events.id"), nullable=False)
    subscriber: Mapped[str] = mapped_column(String(100), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("tenant_id", "event_id", "subscriber"),)


class WebhookReceipt(TenantEntity, Base):
    __tablename__ = "webhook_receipts"
    webhook_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("webhook_endpoints.id"), nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domain_events.id"), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "webhook_id", "digest"),)


class Workflow(TenantEntity, Base):
    __tablename__ = "workflows"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Trigger(TenantEntity, Base):
    __tablename__ = "workflow_triggers"
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)


class Condition(TenantEntity, Base):
    __tablename__ = "workflow_conditions"
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    expression: Mapped[dict] = mapped_column(JSONB, default=dict)


class Action(TenantEntity, Base):
    __tablename__ = "workflow_actions"
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSONB, default=dict)
    position: Mapped[int] = mapped_column(Integer, default=0)


class ExecutionLog(TenantEntity, Base):
    __tablename__ = "workflow_execution_logs"
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domain_events.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    error_code: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (UniqueConstraint("tenant_id", "workflow_id", "event_id"),)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Feature(Base):
    __tablename__ = "features"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)


class PlanFeature(Base):
    __tablename__ = "plan_features"
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id"), primary_key=True)
    feature_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("features.id"), primary_key=True)
    limit_value: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Conversation(TenantEntity, Base):
    __tablename__ = "conversations"
    subject: Mapped[str] = mapped_column(String(255), nullable=False)


class Message(TenantEntity, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class AgentDefinition(TenantEntity, Base):
    """Configuration only; this checkpoint provides no autonomous agent executor."""
    __tablename__ = "agent_definitions"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_tools: Mapped[list] = mapped_column(JSONB, default=list)
