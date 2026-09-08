"""
Celery tasks for AI operations using the new AI Router service.
"""
from celery import shared_task
import structlog
from typing import Dict, Any, Optional
from uuid import UUID

logger = structlog.get_logger()


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_classify_task(self, tenant_id: str, user_id: str, task_type: str, prompt: str, correlation_id: str = None):
    raise ValueError("Use tenant-scoped execute_operation with a persisted AI job ID")


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_score_lead_task(self, tenant_id: str, user_id: str, lead_data: dict, correlation_id: str = None):
    raise ValueError("Use tenant-scoped execute_operation with a persisted AI job ID")


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_generate_email_task(self, tenant_id: str, user_id: str, context: dict, correlation_id: str = None):
    raise ValueError("Use tenant-scoped execute_operation with a persisted AI job ID")


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_analyze_reply_task(self, tenant_id: str, user_id: str, reply_text: str, context: dict, correlation_id: str = None):
    raise ValueError("Use tenant-scoped execute_operation with a persisted AI job ID")


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_next_best_action_task(self, tenant_id: str, user_id: str, lead_data: dict, correlation_id: str = None):
    raise ValueError("Use tenant-scoped execute_operation with a persisted AI job ID")


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_generate_proposal_task(self, tenant_id: str, user_id: str, proposal_data: dict, correlation_id: str = None):
    raise ValueError("Use tenant-scoped execute_operation with a persisted AI job ID")


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_lead_miner_task(self, tenant_id: str, user_id: str, icp_criteria: dict, correlation_id: str = None):
    raise ValueError("Use tenant-scoped execute_operation with a persisted AI job ID")


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_chat_assistant_task(self, tenant_id: str, user_id: str, message: str, context: dict, correlation_id: str = None):
    raise ValueError("Use tenant-scoped execute_operation with a persisted AI job ID")
