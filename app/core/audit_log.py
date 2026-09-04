"""
Audit Logging Service

Provides durable, tamper-resistant audit logging for security-relevant events.
Logs are written to the audit_logs table (protected by RLS) and optionally
to a separate append-only log file for compliance.
"""

import json
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog
from app.core.tenant_context import TenantContext
from app.core.config import get_settings


# Context variable for correlation ID
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class AuditEventType(str, Enum):
    """Standard audit event types."""
    # Authentication
    LOGIN_SUCCESS = "login.success"
    LOGIN_FAILURE = "login.failure"
    LOGOUT = "logout"
    REFRESH_TOKEN_USE = "refresh_token.use"
    REFRESH_TOKEN_REUSE_DETECTED = "refresh_token.reuse_detected"
    REFRESH_TOKEN_REVOKED = "refresh_token.revoked"
    PASSWORD_CHANGE = "password.change"
    PASSWORD_RESET_REQUEST = "password.reset.request"
    PASSWORD_RESET_COMPLETE = "password.reset.complete"
    MFA_ENABLE = "mfa.enable"
    MFA_DISABLE = "mfa.disable"
    
    # User management
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    USER_ACTIVATE = "user.activate"
    USER_DEACTIVATE = "user.deactivate"
    
    # Membership/Role
    MEMBERSHIP_CREATE = "membership.create"
    MEMBERSHIP_UPDATE = "membership.update"
    MEMBERSHIP_DELETE = "membership.delete"
    ROLE_ASSIGN = "role.assign"
    ROLE_ESCALATE_ATTEMPT = "role.escalate.attempt"
    
    # Tenant
    TENANT_CREATE = "tenant.create"
    TENANT_UPDATE = "tenant.update"
    TENANT_DELETE = "tenant.delete"
    TENANT_SETTINGS_CHANGE = "tenant.settings.change"
    
    # Integrations
    INTEGRATION_CREATE = "integration.create"
    INTEGRATION_UPDATE = "integration.update"
    INTEGRATION_DELETE = "integration.delete"
    INTEGRATION_SYNC = "integration.sync"
    INTEGRATION_CREDENTIALS_ROTATE = "integration.credentials.rotate"
    INTEGRATION_CREDENTIALS_VIEW = "integration.credentials.view"
    WEBHOOK_CREATE = "webhook.create"
    WEBHOOK_UPDATE = "webhook.update"
    WEBHOOK_DELETE = "webhook.delete"
    WEBHOOK_SIGNATURE_FAILURE = "webhook.signature.failure"
    
    # Campaigns
    CAMPAIGN_CREATE = "campaign.create"
    CAMPAIGN_UPDATE = "campaign.update"
    CAMPAIGN_DELETE = "campaign.delete"
    CAMPAIGN_SEND = "campaign.send"
    CAMPAIGN_SCHEDULE = "campaign.schedule"
    CAMPAIGN_PAUSE = "campaign.pause"
    CAMPAIGN_RESUME = "campaign.resume"
    
    # Data export/bulk
    DATA_EXPORT = "data.export"
    BULK_IMPORT = "bulk.import"
    BULK_DELETE = "bulk.delete"
    
    # AI
    AI_CONFIGURE = "ai.configure"
    AI_COST_THRESHOLD = "ai.cost.threshold"
    
    # Security
    RATE_LIMIT_EXCEEDED = "rate_limit.exceeded"
    PERMISSION_DENIED = "permission.denied"
    SUSPICIOUS_ACTIVITY = "suspicious.activity"
    
    # Settings
    SECURITY_SETTINGS_CHANGE = "security.settings.change"


class AuditLogger:
    """
    Durable audit logging service.
    
    Writes to database (protected by RLS) and optionally to file.
    Critical events are flushed immediately.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._buffer: List[Dict[str, Any]] = []
        self._buffer_size = 100
        self._critical_events = {
            AuditEventType.LOGIN_FAILURE,
            AuditEventType.REFRESH_TOKEN_REUSE_DETECTED,
            AuditEventType.PERMISSION_DENIED,
            AuditEventType.RATE_LIMIT_EXCEEDED,
            AuditEventType.SUSPICIOUS_ACTIVITY,
            AuditEventType.WEBHOOK_SIGNATURE_FAILURE,
            AuditEventType.ROLE_ESCALATE_ATTEMPT,
        }
    
    def set_correlation_id(self, correlation_id: str) -> None:
        """Set correlation ID for current context."""
        correlation_id_var.set(correlation_id)
    
    def get_correlation_id(self) -> Optional[str]:
        """Get current correlation ID."""
        return correlation_id_var.get()
    
    async def log(
        self,
        event_type: AuditEventType,
        tenant_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: Optional[str] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """
        Log an audit event.
        
        If session is provided, writes within that transaction.
        Otherwise, creates a new session (for standalone logging).
        """
        correlation_id = self.get_correlation_id()
        
        # Prepare log entry
        log_entry = {
            "tenant_id": str(tenant_id),
            "user_id": str(user_id) if user_id else None,
            "action": action or event_type.value,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id else None,
            "old_values": old_values,
            "new_values": self._sanitize_values(new_values),
            "ip_address": ip_address,
            "user_agent": user_agent,
            "success": success,
            "error_message": error_message,
            "correlation_id": correlation_id,
            "metadata": metadata or {},
        }
        
        # Remove None values
        log_entry = {k: v for k, v in log_entry.items() if v is not None}
        
        # Check if critical - flush immediately
        is_critical = event_type in self._critical_events
        
        if session:
            await self._write_to_db(session, log_entry)
            if is_critical:
                await session.flush()
        else:
            # Buffer for batch write
            self._buffer.append(log_entry)
            if len(self._buffer) >= self._buffer_size or is_critical:
                await self._flush_buffer()
    
    def _sanitize_values(self, values: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Remove sensitive fields from logged values."""
        if not values:
            return None
        
        sensitive_fields = {
            "password", "hashed_password", "secret", "secret_key",
            "access_token", "refresh_token", "api_key", "api_secret",
            "client_secret", "webhook_secret", "private_key",
            "credentials", "credentials_encrypted", "token",
            "authorization", "cookie", "session",
        }
        
        sanitized = {}
        for k, v in values.items():
            if k.lower() in sensitive_fields:
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize_values(v)
            else:
                sanitized[k] = v
        
        return sanitized
    
    async def _write_to_db(self, session: AsyncSession, log_entry: Dict[str, Any]) -> None:
        """Write a single log entry to database."""
        stmt = insert(AuditLog).values(**log_entry)
        await session.execute(stmt)
    
    async def _flush_buffer(self) -> None:
        """Flush buffered log entries to database."""
        if not self._buffer:
            return
        
        from app.core.database import get_db_context
        
        async with get_db_context() as session:
            for entry in self._buffer:
                stmt = insert(AuditLog).values(**entry)
                await session.execute(stmt)
            await session.commit()
        
        self._buffer.clear()
    
    async def flush(self) -> None:
        """Manually flush buffer."""
        await self._flush_buffer()


# Global instance
audit_logger = AuditLogger()


async def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    return audit_logger


# Convenience functions for common events
async def log_login_success(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    ip_address: str,
    user_agent: str,
    session: Optional[AsyncSession] = None,
) -> None:
    await audit_logger.log(
        event_type=AuditEventType.LOGIN_SUCCESS,
        tenant_id=tenant_id,
        user_id=user_id,
        action="login",
        resource_type="user",
        resource_id=str(user_id),
        ip_address=ip_address,
        user_agent=user_agent,
        success=True,
        session=session,
    )


async def log_login_failure(
    tenant_id: uuid.UUID,
    email: str,
    ip_address: str,
    user_agent: str,
    reason: str,
    session: Optional[AsyncSession] = None,
) -> None:
    await audit_logger.log(
        event_type=AuditEventType.LOGIN_FAILURE,
        tenant_id=tenant_id,
        action="login",
        resource_type="user",
        resource_id=email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=False,
        error_message=reason,
        metadata={"email": email},
        session=session,
    )


async def log_refresh_token_reuse(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    ip_address: str,
    session: Optional[AsyncSession] = None,
) -> None:
    await audit_logger.log(
        event_type=AuditEventType.REFRESH_TOKEN_REUSE_DETECTED,
        tenant_id=tenant_id,
        user_id=user_id,
        action="refresh_token_reuse",
        resource_type="session",
        resource_id=str(user_id),
        ip_address=ip_address,
        success=False,
        error_message="Refresh token reuse detected - session revoked",
        session=session,
    )


async def log_permission_denied(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    permission: str,
    resource_type: str,
    resource_id: str,
    ip_address: str,
    session: Optional[AsyncSession] = None,
) -> None:
    await audit_logger.log(
        event_type=AuditEventType.PERMISSION_DENIED,
        tenant_id=tenant_id,
        user_id=user_id,
        action="permission_check",
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        success=False,
        error_message=f"Permission denied: {permission}",
        metadata={"required_permission": permission},
        session=session,
    )


async def log_integration_credentials_rotate(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    integration_id: uuid.UUID,
    ip_address: str,
    session: Optional[AsyncSession] = None,
) -> None:
    await audit_logger.log(
        event_type=AuditEventType.INTEGRATION_CREDENTIALS_ROTATE,
        tenant_id=tenant_id,
        user_id=user_id,
        action="credentials_rotate",
        resource_type="integration",
        resource_id=str(integration_id),
        ip_address=ip_address,
        success=True,
        session=session,
    )


async def log_webhook_signature_failure(
    tenant_id: uuid.UUID,
    provider: str,
    webhook_path: str,
    ip_address: str,
    reason: str,
    session: Optional[AsyncSession] = None,
) -> None:
    await audit_logger.log(
        event_type=AuditEventType.WEBHOOK_SIGNATURE_FAILURE,
        tenant_id=tenant_id,
        action="webhook_verification",
        resource_type="webhook",
        resource_id=webhook_path,
        ip_address=ip_address,
        success=False,
        error_message=reason,
        metadata={"provider": provider, "path": webhook_path},
        session=session,
    )


async def log_data_export(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    resource_type: str,
    record_count: int,
    ip_address: str,
    session: Optional[AsyncSession] = None,
) -> None:
    await audit_logger.log(
        event_type=AuditEventType.DATA_EXPORT,
        tenant_id=tenant_id,
        user_id=user_id,
        action="export",
        resource_type=resource_type,
        ip_address=ip_address,
        success=True,
        metadata={"record_count": record_count},
        session=session,
    )