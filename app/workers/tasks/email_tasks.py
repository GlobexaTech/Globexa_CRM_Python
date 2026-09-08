"""Legacy task names fail closed; delivery requires persisted operation IDs."""
from celery import shared_task

@shared_task
def send_email_task(tenant_id: str, to_email: str, subject: str, html_content: str, text_content: str = None):
    raise ValueError("Use conversations API and execute_operation with a persisted job ID")

@shared_task
def send_bulk_email_task(tenant_id: str, campaign_id: str, recipient_ids: list):
    raise ValueError("Use campaign lifecycle API and persisted delivery jobs")

@shared_task
def retry_failed_emails(tenant_id: str):
    from app.workers.tasks.crm_tasks import crm_tick
    return crm_tick.run(tenant_id)

@shared_task
def process_email_webhook(tenant_id: str, provider: str, event_data: dict):
    raise ValueError("Webhook jobs must reference a verified persisted event ID")
