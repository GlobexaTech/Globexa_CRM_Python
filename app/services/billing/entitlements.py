"""SaaS entitlement service - feature flags and usage limits."""

from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta

from app.models import FeatureEntitlement, UsageRecord, Tenant


class EntitlementService:
    """Check feature access and enforce usage limits."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def check_entitlement(
        self,
        tenant_id: UUID,
        feature_key: str,
        quantity: int = 1,
    ) -> bool:
        """Check if tenant has feature enabled and within limits."""
        result = await self.db.execute(
            select(FeatureEntitlement).where(
                FeatureEntitlement.tenant_id == tenant_id,
                FeatureEntitlement.feature_key == feature_key,
                FeatureEntitlement.enabled == True
            )
        )
        entitlement = result.scalar_one_or_none()
        if not entitlement:
            return False
        
        if entitlement.limit_value is not None and entitlement.limit_value != -1:
            # Check current usage in current period
            usage = await self.get_current_usage(tenant_id, feature_key)
            if usage + quantity > entitlement.limit_value:
                return False
        
        return True
    
    async def get_current_usage(
        self,
        tenant_id: UUID,
        metric: str,
    ) -> int:
        """Get current usage for a metric in the current billing period."""
        # Get tenant's subscription to know billing period
        tenant_result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            return 0
        
        # Use current month as period
        now = datetime.utcnow()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if period_start.month == 12:
            period_end = period_start.replace(year=period_start.year + 1, month=1)
        else:
            period_end = period_start.replace(month=period_start.month + 1)
        
        result = await self.db.execute(
            select(func.coalesce(func.sum(UsageRecord.quantity), 0)).where(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.metric == metric,
                UsageRecord.period_start >= period_start,
                UsageRecord.period_end <= period_end,
            )
        )
        return result.scalar() or 0
    
    async def increment_usage(
        self,
        tenant_id: UUID,
        metric: str,
        quantity: int = 1,
        user_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UsageRecord:
        """Record usage for a metric."""
        now = datetime.utcnow()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if period_start.month == 12:
            period_end = period_start.replace(year=period_start.year + 1, month=1)
        else:
            period_end = period_start.replace(month=period_start.month + 1)
        
        # Find existing usage record for this period
        result = await self.db.execute(
            select(UsageRecord).where(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.metric == metric,
                UsageRecord.period_start == period_start,
            )
        )
        usage_record = result.scalar_one_or_none()
        
        if usage_record:
            usage_record.quantity += quantity
            if metadata:
                usage_record.metadata_.update(metadata)
        else:
            usage_record = UsageRecord(
                tenant_id=tenant_id,
                user_id=user_id,
                metric=metric,
                quantity=quantity,
                period_start=period_start,
                period_end=period_end,
                metadata_=metadata or {},
            )
            self.db.add(usage_record)
        
        await self.db.commit()
        await self.db.refresh(usage_record)
        return usage_record
    
    async def get_entitlement(
        self,
        tenant_id: UUID,
        feature_key: str,
    ) -> Optional[FeatureEntitlement]:
        """Get entitlement details."""
        result = await self.db.execute(
            select(FeatureEntitlement).where(
                FeatureEntitlement.tenant_id == tenant_id,
                FeatureEntitlement.feature_key == feature_key,
            )
        )
        return result.scalar_one_or_none()
    
    async def set_entitlement(
        self,
        tenant_id: UUID,
        feature_key: str,
        enabled: bool = True,
        limit_value: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FeatureEntitlement:
        """Set or update feature entitlement."""
        result = await self.db.execute(
            select(FeatureEntitlement).where(
                FeatureEntitlement.tenant_id == tenant_id,
                FeatureEntitlement.feature_key == feature_key,
            )
        )
        entitlement = result.scalar_one_or_none()
        
        if entitlement:
            entitlement.enabled = enabled
            if limit_value is not None:
                entitlement.limit_value = limit_value
            if metadata:
                entitlement.metadata_.update(metadata)
        else:
            entitlement = FeatureEntitlement(
                tenant_id=tenant_id,
                feature_key=feature_key,
                enabled=enabled,
                limit_value=limit_value,
                metadata_=metadata or {},
            )
            self.db.add(entitlement)
        
        await self.db.commit()
        await self.db.refresh(entitlement)
        return entitlement


# Default feature keys for the platform
DEFAULT_FEATURES = {
    "ai_credits": {"enabled": True, "limit": 10000},  # Monthly AI credits
    "users": {"enabled": True, "limit": 5},  # Max users
    "contacts": {"enabled": True, "limit": 10000},  # Max contacts
    "campaigns": {"enabled": True, "limit": 100},  # Max campaigns/month
    "emails": {"enabled": True, "limit": 5000},  # Max emails/month
    "integrations": {"enabled": True, "limit": 10},  # Max integrations
    "workflows": {"enabled": True, "limit": 20},  # Max workflows
    "webhooks": {"enabled": True, "limit": 50},  # Max webhooks
    "api_access": {"enabled": True, "limit": -1},  # Unlimited
    "custom_fields": {"enabled": True, "limit": 50},  # Max custom fields
    "audit_logs": {"enabled": True, "limit": -1},  # Unlimited retention
    "sso": {"enabled": False, "limit": None},  # SSO feature
    "white_label": {"enabled": False, "limit": None},  # White label
}