"""Audit logging for security events."""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
import structlog

from app.core.db_session import AsyncSessionLocal
from app.core.tenant_context import set_tenant_context

logger = structlog.get_logger()


class AuditAction(str, Enum):
    """Standardized audit action types."""
    # Authentication
    LOGIN_SUCCESS = "login.success"
    LOGIN_FAILED = "login.failed"
    LOGOUT = "logout"
    PASSWORD_CHANGE = "password.change"
    PASSWORD_RESET_REQUEST = "password.reset.request"
    PASSWORD_RESET_COMPLETE = "password.reset.complete"
    MFA_ENABLED = "mfa.enabled"
    MFA_DISABLED = "mfa.disabled"
    
    # User management
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    USER_ACTIVATED = "user.activated"
    USER_DEACTIVATED = "user.deactivated"
    
    # Membership/Role
    MEMBERSHIP_CREATED = "membership.created"
    MEMBERSHIP_UPDATED = "membership.updated"
    MEMBERSHIP_DELETED = "membership.deleted"
    ROLE_CHANGED = "role.changed"
    
    # Tenant
    TENANT_CREATED = "tenant.created"
    TENANT_UPDATED = "tenant.updated"
    TENANT_DELETED = "tenant.deleted"
    TENANT_SETTINGS_CHANGED = "tenant.settings_changed"
    
    # Integrations
    INTEGRATION_CREATED = "integration.created"
    INTEGRATION_UPDATED = "integration.updated"
    INTEGRATION_DELETED = "integration.deleted"
    INTEGRATION_CREDENTIALS_ROTATED = "integration.credentials_rotated"
    INTEGRATION_SYNC_STARTED = "integration.sync_started"
    INTEGRATION_SYNC_COMPLETED = "integration.sync_completed"
    INTEGRATION_SYNC_FAILED = "integration.sync_failed"
    WEBHOOK_CREATED = "webhook.created"
    WEBHOOK_UPDATED = "webhook.updated"
    WEBHOOK_DELETED = "webhook.deleted"
    WEBHOOK_VERIFICATION_FAILED = "webhook.verification_failed"
    
    # Campaigns
    CAMPAIGN_CREATED = "campaign.created"
    CAMPAIGN_UPDATED = "campaign.updated"
    CAMPAIGN_DELETED = "campaign.deleted"
    CAMPAIGN_LAUNCHED = "campaign.launched"
    CAMPAIGN_SENT = "campaign.sent"
    CAMPAIGN_PAUSED = "campaign.paused"
    CAMPAIGN_COMPLETED = "campaign.completed"
    
    # Leads/Contacts
    LEAD_CREATED = "lead.created"
    LEAD_UPDATED = "lead.updated"
    LEAD_DELETED = "lead.deleted"
    LEAD_ASSIGNED = "lead.assigned"
    LEAD_CONVERTED = "lead.converted"
    CONTACT_CREATED = "contact.created"
    CONTACT_UPDATED = "contact.updated"
    CONTACT_DELETED = "contact.deleted"
    BULK_IMPORT = "bulk.import"
    BULK_EXPORT = "bulk.export"
    
    # Deals/Pipeline
    DEAL_CREATED = "deal.created"
    DEAL_UPDATED = "deal.updated"
    DEAL_DELETED = "deal.deleted"
    DEAL_STAGE_CHANGED = "deal.stage_changed"
    PIPELINE_CREATED = "pipeline.created"
    PIPELINE_UPDATED = "pipeline.updated"
    PIPELINE_STAGE_CHANGED = "pipeline_stage.changed"
    
    # AI
    AI_CONFIG_CHANGED = "ai.config_changed"
    AI_USAGE_LOGGED = "ai.usage_logged"
    
    # Security
    PERMISSION_DENIED = "security.permission_denied"
    RATE_LIMIT_EXCEEDED = "security.rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "security.suspicious_activity"
    TOKEN_REFRESH = "token.refresh"
    TOKEN_REVOKED = "token.revoked"


class AuditSeverity(str, Enum):
    """Audit event severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Audit event data structure."""
    action: AuditAction
    tenant_id: uuid.UUID
    actor_id: Optional[uuid.UUID] = None
    actor_type: str = "user"  # user, system, api
    object_type: Optional[str] = None
    object_id: Optional[uuid.UUID] = None
    severity: AuditSeverity = AuditSeverity.INFO
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    request_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    # Computed
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/logging."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat(),
            "action": self.action.value,
            "tenant_id": str(self.tenant_id),
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "actor_type": self.actor_type,
            "object_type": self.object_type,
            "object_id": str(self.object_id) if self.object_id else None,
            "severity": self.severity.value,
            "description": self.description,
            "metadata": self.metadata,
            "request_id": self.request_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }


class AuditLogger:
    """Service for logging audit events."""
    
    def __init__(self):
        self._buffer: List[AuditEvent] = []
        self._buffer_size = 100
    
    async def log(self, event: AuditEvent) -> None:
        """Log an audit event (async, fire-and-forget with buffering)."""
        # Add to buffer
        self._buffer.append(event)
        
        # Also log to structlog for immediate visibility
        logger.log(
            event.severity.value.upper(),
            "audit",
            **event.to_dict()
        )
        
        # Flush buffer if full
        if len(self._buffer) >= self._buffer_size:
            await self.flush()
    
    async def flush(self) -> None:
        """Flush buffered events to database."""
        if not self._buffer:
            return
        
        events = self._buffer
        self._buffer = []
        
        try:
            async with AsyncSessionLocal() as session:
                # Import here to avoid circular import
                from app.models import AuditLog
                
                # Set tenant context if all events belong to same tenant
                tenant_ids = {e.tenant_id for e in events}
                if len(tenant_ids) == 1:
                    await set_tenant_context(session, tenant_ids.pop())
                
                for event in events:
                    log_entry = AuditLog(
                        id=event.id,
                        tenant_id=event.tenant_id,
                        actor_id=event.actor_id,
                        actor_type=event.actor_type,
                        action=event.action.value,
                        object_type=event.object_type,
                        object_id=event.object_id,
                        severity=event.severity.value,
                        description=event.description,
                        metadata_=event.metadata,
                        request_id=event.request_id,
                        ip_address=event.ip_address,
                        user_agent=event.user_agent,
                        created_at=event.timestamp,
                    )
                    session.add(log_entry)
                
                await session.commit()
        except Exception as e:
            logger.error("Failed to flush audit logs", error=str(e))
            # Re-buffer failed events
            self._buffer = events + self._buffer
    
    async def log_event(
        self,
        action: AuditAction,
        tenant_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
        actor_type: str = "user",
        object_type: Optional[str] = None,
        object_id: Optional[uuid.UUID] = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Convenience method to create and log an event."""
        event = AuditEvent(
            action=action,
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_type=actor_type,
            object_type=object_type,
            object_id=object_id,
            severity=severity,
            description=description,
            metadata=metadata or {},
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.log(event)


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


# Convenience functions for common audit events
async def audit_login_success(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    request_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Log successful login."""
    await get_audit_logger().log_event(
        action=AuditAction.LOGIN_SUCCESS,
        tenant_id=tenant_id,
        actor_id=user_id,
        severity=AuditSeverity.INFO,
        description="User logged in successfully",
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


async def audit_login_failed(
    tenant_id: uuid.UUID,
    email: str,
    reason: str,
    request_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Log failed login attempt."""
    await get_audit_logger().log_event(
        action=AuditAction.LOGIN_FAILED,
        tenant_id=tenant_id,
        actor_type="user",
        severity=AuditSeverity.WARNING,
        description=f"Login failed for {email}: {reason}",
        metadata={"email": email, "failure_reason": reason},
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


async def audit_permission_denied(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    permission: str,
    resource: str,
    request_id: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Log permission denied event."""
    await get_audit_logger().log_event(
        action=AuditAction.PERMISSION_DENIED,
        tenant_id=tenant_id,
        actor_id=user_id,
        severity=AuditSeverity.WARNING,
        description=f"Permission denied: {permission} on {resource}",
        metadata={"permission": permission, "resource": resource},
        request_id=request_id,
        ip_address=ip_address,
    )


async def audit_credential_rotation(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    integration_id: uuid.UUID,
    credential_type: str,
    request_id: Optional[str] = None,
) -> None:
    """Log integration credential rotation."""
    await get_audit_logger().log_event(
        action=AuditAction.INTEGRATION_CREDENTIALS_ROTATED,
        tenant_id=tenant_id,
        actor_id=actor_id,
        object_type="integration",
        object_id=integration_id,
        severity=AuditSeverity.INFO,
        description=f"Rotated {credential_type} credentials for integration",
        metadata={"credential_type": credential_type},
        request_id=request_id,
    )


async def audit_campaign_launch(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    campaign_id: uuid.UUID,
    recipient_count: int,
    request_id: Optional[str] = None,
) -> None:
    """Log campaign launch."""
    await get_audit_logger().log_event(
        action=AuditAction.CAMPAIGN_LAUNCHED,
        tenant_id=tenant_id,
        actor_id=actor_id,
        object_type="campaign",
        object_id=campaign_id,
        severity=AuditSeverity.INFO,
        description=f"Campaign launched to {recipient_count} recipients",
        metadata={"recipient_count": recipient_count},
        request_id=request_id,
    )


async def audit_bulk_export(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    resource_type: str,
    record_count: int,
    request_id: Optional[str] = None,
) -> None:
    """Log bulk data export."""
    await get_audit_logger().log_event(
        action=AuditAction.BULK_EXPORT,
        tenant_id=tenant_id,
        actor_id=actor_id,
        severity=AuditSeverity.INFO,
        description=f"Exported {record_count} {resource_type} records",
        metadata={"resource_type": resource_type, "record_count": record_count},
        request_id=request_id,
    )