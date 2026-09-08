"""
Celery tasks for usage metering and billing.
"""
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from datetime import datetime, timedelta, timezone
import structlog

from app.core.tenant_context import tenant_db_context
from app.models import UsageRecord, AuditLog, Subscription, SubscriptionStatusEnum, Tenant

logger = structlog.get_logger()


@shared_task
def aggregate_daily_usage(tenant_id: str):
    """Aggregate daily usage metrics for all tenants."""
    logger.info("Aggregating daily usage")
    # This runs daily at 1 AM
    # TODO: Calculate daily totals for emails, AI credits, contacts, etc.
    # Store in usage_records with period_start/period_end
    return {"status": "completed"}


@shared_task
def record_usage(tenant_id: str, user_id: str = None, metric: str = "api_calls", quantity: int = 1, metadata: dict = None):
    """Record a usage event."""
    logger.info("Recording usage", tenant_id=tenant_id, metric=metric, quantity=quantity)
    
    async def _record():
        async with tenant_db_context(tenant_id) as db:
            # Get current period (daily)
            now = datetime.now(timezone.utc)
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            period_end = period_start + timedelta(days=1)
            
            usage = UsageRecord(
                tenant_id=tenant_id,
                user_id=user_id,
                metric=metric,
                quantity=quantity,
                period_start=period_start,
                period_end=period_end,
                metadata_=metadata or {},
            )
            db.add(usage)
            await db.commit()
    
    import asyncio
    asyncio.run(_record())
    return {"status": "recorded"}


@shared_task
def check_subscription_status(tenant_id: str):
    """Check and update subscription statuses."""
    logger.info("Checking subscription statuses")
    
    async def _check():
        async with tenant_db_context(tenant_id) as db:
            now = datetime.now(timezone.utc)
            
            # Find trials ending soon
            result = await db.execute(
                select(Subscription).where(
                    Subscription.status == SubscriptionStatusEnum.TRIALING,
                    Subscription.trial_end != None,
                    Subscription.trial_end <= now + timedelta(days=3),
                )
            )
            expiring_trials = result.scalars().all()
            
            for sub in expiring_trials:
                # TODO: Send notification email
                logger.warning("Trial ending soon", tenant_id=str(sub.tenant_id), trial_end=sub.trial_end)
            
            # Find past due subscriptions
            result = await db.execute(
                select(Subscription).where(
                    Subscription.status == SubscriptionStatusEnum.ACTIVE,
                    Subscription.current_period_end != None,
                    Subscription.current_period_end < now,
                )
            )
            past_due = result.scalars().all()
            
            for sub in past_due:
                sub.status = SubscriptionStatusEnum.PAST_DUE
                logger.warning("Subscription past due", tenant_id=str(sub.tenant_id))
            
            await db.commit()
    
    import asyncio
    asyncio.run(_check())
    return {"status": "completed"}


@shared_task
def cleanup_old_audit_logs(tenant_id: str):
    """Clean up audit logs older than retention period (1 year)."""
    logger.info("Cleaning up old audit logs")
    
    async def _cleanup():
        async with tenant_db_context(tenant_id) as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=365)
            result = await db.execute(
                delete(AuditLog).where(AuditLog.created_at < cutoff)
            )
            deleted = result.rowcount
            await db.commit()
            logger.info("Deleted old audit logs", count=deleted)
    
    import asyncio
    asyncio.run(_cleanup())
    return {"status": "completed"}


@shared_task
def enforce_usage_limits(tenant_id: str, metric: str, limit: int):
    """Check if tenant has exceeded usage limit."""
    logger.info("Enforcing usage limits", tenant_id=tenant_id, metric=metric, limit=limit)
    
    async def _check():
        async with tenant_db_context(tenant_id) as db:
            now = datetime.now(timezone.utc)
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            period_end = period_start + timedelta(days=1)
            
            result = await db.execute(
                select(func.sum(UsageRecord.quantity)).where(
                    UsageRecord.tenant_id == tenant_id,
                    UsageRecord.metric == metric,
                    UsageRecord.period_start >= period_start,
                    UsageRecord.period_end <= period_end,
                )
            )
            used = result.scalar() or 0
            
            return {
                "allowed": used < limit,
                "used": used,
                "limit": limit,
                "remaining": max(0, limit - used),
            }
    
    import asyncio
    return asyncio.run(_check())