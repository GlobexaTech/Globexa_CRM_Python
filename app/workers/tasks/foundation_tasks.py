"""Tenant-explicit event processing and retryable outbox delivery."""
import asyncio
from uuid import UUID
from celery import shared_task
from app.core.tenant_context import tenant_db_context
from app.core.events import CeleryPublisher, dispatch_event, drain_outbox


@shared_task
def publish_outbox(tenant_id: str):
    async def run():
        async with tenant_db_context(tenant_id) as db:
            return await drain_outbox(db, CeleryPublisher())
    return asyncio.run(run())


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def deliver_event(tenant_id: str, event_id: str):
    async def run():
        async with tenant_db_context(tenant_id) as db:
            await dispatch_event(db, UUID(event_id))
    return asyncio.run(run())


@shared_task
def dispatch_scheduled():
    """Global registry enumeration only; never queries tenant-owned business tables."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.core.config import get_settings
    from app.models import Tenant
    from app.workers.tasks.crm_tasks import crm_tick
    async def run():
        engine = create_async_engine(get_settings().database.url, poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as db:
                ids = (await db.scalars(text("SELECT public.active_tenant_ids()"))).all()
            for tenant_id in ids:
                for task in (publish_outbox, crm_tick):
                    task.delay(tenant_id=str(tenant_id))
            return len(ids)
        finally:
            await engine.dispose()
    return asyncio.run(run())
