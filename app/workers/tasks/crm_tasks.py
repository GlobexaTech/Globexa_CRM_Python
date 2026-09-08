"""Bounded tenant-explicit scheduling and execution for CRM operations."""

import asyncio
from uuid import UUID
from celery import shared_task
from sqlalchemy import select
from app.core.tenant_context import tenant_db_context
from app.services.crm.common import now
from app.models import (
    OperationJob,
    Campaign,
    CampaignStatusEnum,
    Task,
    TaskStatusEnum,
    DomainEvent,
    Integration,
)


@shared_task(autoretry_for=(ConnectionError,), retry_backoff=True, max_retries=3)
def execute_operation(tenant_id: str, job_id: str):
    from app.services.crm.jobs import execute_job

    async def run():
        async with tenant_db_context(tenant_id) as db:
            await execute_job(db, UUID(tenant_id), UUID(job_id))

    return asyncio.run(run())


@shared_task
def crm_tick(tenant_id: str):
    async def run():
        tenant = UUID(tenant_id)
        async with tenant_db_context(tenant_id) as db:
            await schedule_due(db, tenant)
            ids = list(
                (
                    await db.scalars(
                        select(OperationJob.id)
                        .where(
                            OperationJob.tenant_id == tenant,
                            OperationJob.status.in_(["pending", "retry", "running"]),
                            OperationJob.available_at <= now(),
                        )
                        .order_by(OperationJob.available_at, OperationJob.id)
                        .limit(25)
                    )
                ).all()
            )
        # Queue only committed IDs. Duplicate deliveries are fenced by job row locks.
        for job_id in ids:
            execute_operation.delay(tenant_id=tenant_id, job_id=str(job_id))
        return len(ids)

    return asyncio.run(run())


async def schedule_due(db, tenant_id):
    from app.services.crm.common import serial_key

    await serial_key(db, tenant_id, "crm-scheduler")
    from app.services.crm.campaigns import transition, update_stats
    from app.core.events import publish_event
    from app.services.crm.integrations import request_sync
    from fastapi import HTTPException
    from app.services.crm.providers import ProviderFailure
    from datetime import timedelta
    from app.services.crm.providers import adapter_for

    campaigns = (
        await db.scalars(
            select(Campaign)
            .where(
                Campaign.tenant_id == tenant_id,
                Campaign.status == CampaignStatusEnum.SCHEDULED,
                Campaign.scheduled_at <= now(),
            )
            .limit(25)
            .with_for_update(skip_locked=True)
        )
    ).all()
    for campaign in campaigns:
        try:
            async with db.begin_nested():
                await transition(
                    db, tenant_id, campaign.created_by_id, campaign.id, "launch"
                )
        except (HTTPException, ProviderFailure):
            campaign.status = CampaignStatusEnum.FAILED
    running = (
        await db.scalars(
            select(Campaign.id)
            .where(
                Campaign.tenant_id == tenant_id,
                Campaign.status == CampaignStatusEnum.SENDING,
            )
            .limit(25)
        )
    ).all()
    for campaign_id in running:
        await update_stats(db, tenant_id, campaign_id)
    tasks = (
        await db.scalars(
            select(Task)
            .where(
                Task.tenant_id == tenant_id,
                Task.due_date < now(),
                Task.completed_at.is_(None),
                Task.status != TaskStatusEnum.COMPLETED,
            )
            .limit(100)
        )
    ).all()
    for task in tasks:
        key = "overdue:" + str(task.id) + ":" + task.due_date.isoformat()
        existing = await db.scalar(
            select(DomainEvent.id).where(
                DomainEvent.tenant_id == tenant_id, DomainEvent.idempotency_key == key
            )
        )
        if not existing:
            publish_event(
                db,
                tenant_id=tenant_id,
                actor_id=task.created_by_id,
                event_type="task.overdue",
                aggregate_id=task.id,
                payload={
                    k: str(getattr(task, k))
                    for k in ("lead_id", "deal_id", "contact_id", "company_id")
                    if getattr(task, k)
                },
                idempotency_key=key,
            )
    integrations = (
        await db.scalars(
            select(Integration)
            .where(
                Integration.tenant_id == tenant_id,
                Integration.sync_enabled.is_(True),
                Integration.status == "connected",
            )
            .limit(25)
        )
    ).all()
    for integration in integrations:
        minutes = max(5, integration.sync_frequency_minutes)
        if (
            not integration.created_by_id
            or "sync" not in adapter_for(integration).capabilities
        ):
            continue
        if integration.last_sync_at and integration.last_sync_at > now() - timedelta(
            minutes=minutes
        ):
            continue
        pending = await db.scalar(
            select(OperationJob.id)
            .where(
                OperationJob.tenant_id == tenant_id,
                OperationJob.kind == "sync",
                OperationJob.payload["integration_id"].astext == str(integration.id),
                OperationJob.status.in_(["pending", "retry", "running"]),
            )
            .limit(1)
        )
        if not pending:
            try:
                async with db.begin_nested():
                    bucket = int(now().timestamp()) // (minutes * 60)
                    await request_sync(
                        db,
                        tenant_id,
                        integration.created_by_id,
                        integration.id,
                        f"scheduled:{integration.id}:{bucket}",
                    )
            except (HTTPException, ProviderFailure):
                continue
