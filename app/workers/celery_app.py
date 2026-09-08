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
        "app.workers.tasks.foundation_tasks",
        "app.workers.tasks.crm_tasks",
    ],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
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

# System dispatcher enumerates the global tenant registry only; child jobs are scoped.
celery_app.conf.beat_schedule = {
    "tenant-tick": {"task": "app.workers.tasks.foundation_tasks.dispatch_scheduled", "schedule": 60.0},
}
__all__ = ["celery_app"]
