"""Compatibility task names delegate to durable campaign operations."""
import asyncio
from uuid import UUID
from celery import shared_task
from sqlalchemy import select
from app.core.tenant_context import tenant_db_context

@shared_task
def send_campaign_task(tenant_id: str, campaign_id: str, user_id: str):
    from app.services.crm.campaigns import transition
    async def run():
        async with tenant_db_context(tenant_id, user_id) as db:
            return await transition(db, UUID(tenant_id), UUID(user_id), UUID(campaign_id), "launch")
    return asyncio.run(run())

@shared_task
def process_scheduled_campaigns(tenant_id: str):
    from app.workers.tasks.crm_tasks import crm_tick
    return crm_tick.run(tenant_id)

@shared_task
def retry_failed_emails(tenant_id: str):
    from app.workers.tasks.crm_tasks import crm_tick
    return crm_tick.run(tenant_id)

@shared_task
def aggregate_campaign_stats(tenant_id: str):
    from app.models import Campaign
    from app.services.crm.campaigns import update_stats
    async def run():
        async with tenant_db_context(tenant_id) as db:
            ids = (await db.scalars(select(Campaign.id).where(Campaign.tenant_id == UUID(tenant_id)).limit(100))).all()
            for campaign_id in ids:
                await update_stats(db, UUID(tenant_id), campaign_id)
    return asyncio.run(run())

@shared_task
def process_email_webhook(tenant_id: str, provider: str, payload: dict):
    raise ValueError("Use verified webhook ingress and persisted event IDs")
