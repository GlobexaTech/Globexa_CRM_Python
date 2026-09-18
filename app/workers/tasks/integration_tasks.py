"""Legacy task names fail closed; provider work requires a persisted operation job."""
from celery import shared_task


@shared_task(bind=True)
def sync_integration_task(self, tenant_id: str, integration_id: str, sync_type: str = "incremental", cursor: str = None):
    raise ValueError("Use execute_operation with a permission-checked persisted sync job")


@shared_task
def process_inbound_webhook_task(tenant_id: str, source: str, payload: dict):
    raise ValueError("Use signed webhook ingress and its persisted receipt operation")
