"""Compatibility task names route only to durable, tenant-scoped operations."""
from celery import shared_task


@shared_task(bind=True)
def sync_integration_task(self, tenant_id: str, integration_id: str, sync_log_id: str, full_sync: bool = False):
    raise ValueError("Use execute_operation with a persisted integration sync job ID")


@shared_task
def process_webhook_task(tenant_id: str, event_id: str):
    from app.workers.tasks.foundation_tasks import deliver_event
    return deliver_event.run(tenant_id=tenant_id, event_id=event_id)


@shared_task
def scheduled_integration_sync(tenant_id: str):
    from app.workers.tasks.crm_tasks import crm_tick
    return crm_tick.run(tenant_id)


@shared_task
def validate_all_integrations(tenant_id: str):
    raise ValueError("Use the permission-checked integration validation API")
