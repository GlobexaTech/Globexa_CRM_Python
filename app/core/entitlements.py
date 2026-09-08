"""Data-driven SaaS limits; serialize concurrent consumption on an entitlement row."""
from datetime import datetime, timezone
from sqlalchemy import func, select
from app.models import FeatureEntitlement, UsageRecord, Plan, Feature, PlanFeature


class EntitlementDenied(PermissionError):
    pass


class EntitlementService:
    def __init__(self, db):
        self.db = db

    async def provision(self, tenant_id, plan_key):
        rows = (await self.db.execute(select(Feature, PlanFeature).join(
            PlanFeature, PlanFeature.feature_id == Feature.id).join(Plan).where(Plan.key == plan_key))).all()
        for feature, rule in rows:
            self.db.add(FeatureEntitlement(tenant_id=tenant_id, feature_key=feature.key,
                                           enabled=rule.enabled, limit_value=rule.limit_value))
        await self.db.flush()

    async def consume(self, tenant_id, feature_key, quantity=1, user_id=None):
        if quantity <= 0:
            raise ValueError("Consumption must be positive")
        rule = await self.db.scalar(select(FeatureEntitlement).where(
            FeatureEntitlement.tenant_id == tenant_id,
            FeatureEntitlement.feature_key == feature_key).with_for_update())
        if not rule or not rule.enabled:
            raise EntitlementDenied("Feature is not enabled")
        start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        used = await self.db.scalar(select(func.coalesce(func.sum(UsageRecord.quantity), 0)).where(
            UsageRecord.tenant_id == tenant_id, UsageRecord.metric == feature_key,
            UsageRecord.created_at >= start))
        if rule.limit_value is not None and rule.limit_value >= 0 and used + quantity > rule.limit_value:
            raise EntitlementDenied("Feature limit exceeded")
        self.db.add(UsageRecord(tenant_id=tenant_id, user_id=user_id, metric=feature_key,
                                quantity=quantity, period_start=start,
                                period_end=datetime.now(timezone.utc)))
        await self.db.flush()
