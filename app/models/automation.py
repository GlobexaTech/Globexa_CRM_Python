"""Versioned automation records. Tenant compound keys are enforced by migration 018."""

import uuid
from datetime import datetime
from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.foundation import TenantEntity


class Automation(TenantEntity, Base):
    __tablename__ = "automations"
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    draft: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AutomationVersion(TenantEntity, Base):
    __tablename__ = "automation_versions"
    automation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automations.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict] = mapped_column(JSONB)
    digest: Mapped[str] = mapped_column(String(64))
    published_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (UniqueConstraint("tenant_id", "automation_id", "number"),)


class AutomationTrigger(TenantEntity, Base):
    __tablename__ = "automation_triggers"
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automation_versions.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)


class AutomationCondition(TenantEntity, Base):
    __tablename__ = "automation_conditions"
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automation_versions.id"), index=True)
    node_key: Mapped[str] = mapped_column(String(50))
    expression: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("tenant_id", "version_id", "node_key"),)


class AutomationAction(TenantEntity, Base):
    __tablename__ = "automation_actions"
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automation_versions.id"), index=True)
    node_key: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(50))
    arguments: Mapped[dict] = mapped_column(JSONB, default=dict)
    __table_args__ = (UniqueConstraint("tenant_id", "version_id", "node_key"),)


class AutomationExecution(TenantEntity, Base):
    __tablename__ = "automation_executions"
    automation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automations.id"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automation_versions.id"), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("domain_events.id"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("automation_executions.id"))
    chain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, index=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    visited: Mapped[list] = mapped_column(JSONB, default=list)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    current_node: Mapped[str | None] = mapped_column(String(50))
    input: Mapped[dict] = mapped_column(JSONB, default=dict)
    output: Mapped[dict] = mapped_column(JSONB, default=dict)
    step_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_calls: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resume_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key"),
        Index("ix_automation_execution_queue", "tenant_id", "state", "resume_at"),
    )


class AutomationStepExecution(TenantEntity, Base):
    __tablename__ = "automation_step_executions"
    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_executions.id"), index=True
    )
    node_key: Mapped[str] = mapped_column(String(50))
    state: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    input: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resume_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("approval_requests.id"))
    child_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("operation_jobs.id"))
    __table_args__ = (UniqueConstraint("tenant_id", "execution_id", "node_key"),)


class AutomationSchedule(TenantEntity, Base):
    __tablename__ = "automation_schedules"
    automation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automations.id"), index=True)
    timezone: Mapped[str] = mapped_column(String(100))
    configuration: Mapped[dict] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("tenant_id", "automation_id"),)


class AutomationVariable(TenantEntity, Base):
    __tablename__ = "automation_variables"
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automation_versions.id"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    value: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("tenant_id", "version_id", "name"),)


class AutomationCredentialReference(TenantEntity, Base):
    __tablename__ = "automation_credential_references"
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automation_versions.id"), index=True)
    integration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integrations.id"))
    name: Mapped[str] = mapped_column(String(50))
    __table_args__ = (UniqueConstraint("tenant_id", "version_id", "name"),)


class AutomationPolicy(TenantEntity, Base):
    __tablename__ = "automation_policies"
    limits: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (UniqueConstraint("tenant_id"),)


class AutomationNotification(TenantEntity, Base):
    __tablename__ = "automation_notifications"
    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_executions.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(String(2000))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
