"""CRM operations extend existing entities; all records are tenant owned."""

from datetime import datetime
from uuid import UUID
from sqlalchemy import (
    String,
    Text,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.core.credentials import EncryptedText
from app.models.foundation import TenantEntity


class Participant(TenantEntity, Base):
    __tablename__ = "conversation_participants"
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"))
    address: Mapped[str] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (UniqueConstraint("tenant_id", "conversation_id", "address"),)


class AnalyticsEvent(TenantEntity, Base):
    __tablename__ = "analytics_events"
    event_id: Mapped[UUID | None] = mapped_column(ForeignKey("domain_events.id"))
    event_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100))
    value: Mapped[float | None] = mapped_column(Float)
    dimensions: Mapped[dict] = mapped_column(JSONB, default=dict)
    __table_args__ = (UniqueConstraint("tenant_id", "event_id"),)


class OperationJob(TenantEntity, Base):
    __tablename__ = "operation_jobs"
    kind: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)


class AIInsight(TenantEntity, Base):
    __tablename__ = "ai_insights"
    job_id: Mapped[UUID] = mapped_column(ForeignKey("operation_jobs.id"))
    capability: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[UUID | None]
    output: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("tenant_id", "job_id"),)


class OAuthSession(TenantEntity, Base):
    __tablename__ = "oauth_sessions"
    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integrations.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    verifier: Mapped[str] = mapped_column(EncryptedText())
    redirect_uri: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowRevision(TenantEntity, Base):
    __tablename__ = "workflow_revisions"
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"))
    version: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("tenant_id", "workflow_id", "version"),)


class Lead(TenantEntity, Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    # Lead details
    first_name: Mapped[String] = mapped_column(String(100), nullable=True)
    last_name: Mapped[String] = mapped_column(String(100), nullable=True)
    email: Mapped[String] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[String] = mapped_column(String(50), nullable=True)
    title: Mapped[String] = mapped_column(String(255), nullable=True)
    company_name: Mapped[String] = mapped_column(String(255), nullable=True)
    # Lead status
    status: Mapped[String] = mapped_column(String(50), nullable=False, server_default="new")
    value: Mapped[Integer] = mapped_column(Integer, nullable=True)  # in cents
    # Lead source
    source: Mapped[String] = mapped_column(String(100), nullable=True, index=True)
    source_id: Mapped[String] = mapped_column(String(255), nullable=True, index=True)
    # Timestamps
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="leads")


class Contact(TenantEntity, Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    # Contact details
    first_name: Mapped[String] = mapped_column(String(100), nullable=True)
    last_name: Mapped[String] = mapped_column(String(100), nullable=True)
    email: Mapped[String] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[String] = mapped_column(String(50), nullable=True)
    title: Mapped[String] = mapped_column(String(255), nullable=True)
    company_name: Mapped[String] = mapped_column(String(255), nullable=True)
    # Contact status
    status: Mapped[String] = mapped_column(String(50), nullable=False, server_default="active")
    # Timestamps
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="contacts")
