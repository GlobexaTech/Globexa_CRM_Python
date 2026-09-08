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
