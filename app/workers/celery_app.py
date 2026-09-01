"""
Celery configuration for Globexa CRM background workers.
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "globexa_crm",
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
    include=[
        "app.workers.tasks.email_tasks",
        "app.workers.tasks.campaign_tasks_v2",
        "app.workers.tasks.ai_tasks_v2",
        "app.workers.tasks.integration_tasks_v2",
        "app.workers.tasks.usage_tasks",
    ],
)

# Celery configuration
celery_app.conf.update(
    task_serializer=settings.celery.task_serializer,
    result_serializer=settings.celery.result_serializer,
    accept_content=settings.celery.accept_content,
    timezone=settings.celery.timezone,
    enable_utc=settings.celery.enable_utc,
    task_track_started=settings.celery.task_track_started,
    task_time_limit=settings.celery.task_time_limit,
    task_soft_time_limit=settings.celery.task_soft_time_limit,
    worker_prefetch_multiplier=settings.celery.worker_prefetch_multiplier,
    worker_max_tasks_per_child=settings.celery.worker_max_tasks_per_child,
    beat_schedule=settings.celery.beat_schedule,
    # Result backend settings
    result_expires=3600,
    result_compression='gzip',
    # Task routing - V2 tasks
    task_routes={
        "app.workers.tasks.email_tasks.*": {"queue": "emails"},
        "app.workers.tasks.campaign_tasks_v2.*": {"queue": "campaigns"},
        "app.workers.tasks.ai_tasks_v2.*": {"queue": "ai"},
        "app.workers.tasks.integration_tasks_v2.*": {"queue": "integrations"},
        "app.workers.tasks.usage_tasks.*": {"queue": "usage"},
    },
    # Worker settings
    worker_disable_rate_limits=False,
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Periodic tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    # Daily usage aggregation
    "aggregate-daily-usage": {
        "task": "app.workers.tasks.usage_tasks.aggregate_daily_usage",
        "schedule": crontab(hour=1, minute=0),  # 1 AM daily
    },
    # Cleanup old audit logs (keep 1 year)
    "cleanup-audit-logs": {
        "task": "app.workers.tasks.usage_tasks.cleanup_old_audit_logs",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),  # Weekly Sunday 2 AM
    },
    # Check subscription status
    "check-subscriptions": {
        "task": "app.workers.tasks.usage_tasks.check_subscription_status",
        "schedule": crontab(hour=3, minute=0),  # Daily 3 AM
    },
    # Process scheduled campaigns
    "process-scheduled-campaigns": {
        "task": "app.workers.tasks.campaign_tasks_v2.process_scheduled_campaigns",
        "schedule": 60.0,  # Every minute
    },
    # Retry failed email sends
    "retry-failed-emails": {
        "task": "app.workers.tasks.email_tasks.retry_failed_emails",
        "schedule": 300.0,  # Every 5 minutes
    },
}


# For direct imports
__all__ = ["celery_app"]