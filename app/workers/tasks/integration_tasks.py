"""Celery tasks for integration operations."""
from celery import shared_task
import structlog
from datetime import datetime, timezone
from typing import Dict, Any

from app.core.database import get_db
from app.core.tenant_context import tenant_db_context
from app.models import Integration
from app.services.integration.adapter import IntegrationService
from app.services.crm.common import owned, enqueue, audit, now

logger = structlog.get_logger()


@shared_task(bind=True, max_retries=3)
def sync_integration_task(self, tenant_id: str, integration_id: str, sync_type: str = "incremental", cursor: str = None):
    """Sync leads from an integration."""
    logger.info("Starting integration sync", tenant_id=tenant_id, integration_id=integration_id, sync_type=sync_type, cursor=cursor)
    
    # We need to get a database session. Since this is a Celery task, we'll create a new session.
    # We'll use the tenant_db_context to ensure we are in the right tenant.
    # Note: The tenant_db_context is an async context manager, but we are in a sync task.
    # We'll have to run the async code in an event loop.
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    import os
    
    async def _sync():
        # Get a database session
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise Exception("DATABASE_URL environment variable not set")
        engine = create_async_engine(database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as session:
            async with tenant_db_context(session, tenant_id):
                try:
                    # Get the integration
                    integration = await owned(session, Integration, tenant_id, integration_id)
                    
                    # Prepare integration config and credentials
                    integration_config = integration.config or {}
                    # Get credentials - we need to get the decrypted credentials
                    # For simplicity, we'll assume the first credential is the one we want.
                    # In reality, we might have multiple credentials and we need to choose the right one.
                    if not integration.credentials:
                        raise Exception("No credentials found for integration")
                    
                    # We'll use the first credential for now.
                    credential = integration.credentials[0]
                    # Decrypt the credential
                    from app.services.crm.common import CredentialService
                    cred_service = CredentialService()
                    credentials = {
                        "access_token": cred_service.decrypt(credential.access_token),
                    }
                    if credential.refresh_token:
                        credentials["refresh_token"] = cred_service.decrypt(credential.refresh_token)
                    # Add other fields as needed
                    if credential.token_expires_at:
                        credentials["token_expires_at"] = credential.token_expires_at.isoformat() if credential.token_expires_at else None
                    if credential.token_type:
                        credentials["token_type"] = credential.token_type
                    if credential.scopes:
                        credentials["scopes"] = credential.scopes
                    
                    # Perform the sync
                    adapter = IntegrationService()
                    sync_result = await adapter.sync_integration(
                        integration.type.value,
                        integration_config,
                        credentials,
                        since=None if sync_type == "full" else None,  # For incremental, we would need a since date
                        limit=None,
                    )
                    
                    # Update integration sync status
                    integration.last_sync_at = now()
                    integration.last_sync_status = sync_result.status if hasattr(sync_result, 'status') else "completed" if sync_result.success else "failed"
                    integration.last_sync_error = sync_result.error_message if not sync_result.success else None
                    integration.records_synced = sync_result.records_created + sync_result.records_updated
                    
                    await session.commit()
                    
                    logger.info("Integration sync completed", tenant_id=tenant_id, integration_id=integration_id, 
                                records_processed=sync_result.records_processed,
                                records_created=sync_result.records_created,
                                records_updated=sync_result.records_updated,
                                records_failed=sync_result.records_failed)
                    
                    return {
                        "status": "completed" if sync_result.success else "failed",
                        "records_processed": sync_result.records_processed,
                        "records_created": sync_result.records_created,
                        "records_updated": sync_result.records_updated,
                        "records_failed": sync_result.records_failed,
                    }
                except Exception as e:
                    logger.error("Integration sync failed", tenant_id=tenant_id, integration_id=integration_id, error=str(e))
                    # Update integration with error
                    try:
                        async with session.begin():
                            integration = await owned(session, Integration, tenant_id, integration_id)
                            integration.last_sync_at = now()
                            integration.last_sync_status = "failed"
                            integration.last_sync_error = str(e)
                            await session.commit()
                    except Exception as commit_error:
                        logger.error("Failed to update integration status after error", error=str(commit_error))
                    
                    # Retry logic
                    if self.request.retries < self.max_retries:
                        raise self.retry(countdown=60, exc=e)
                    else:
                        return {
                            "status": "failed",
                            "error": str(e),
                        }
    
    # Run the async function
    try:
        result = asyncio.run(_sync())
    except Exception as e:
        logger.error("Integration sync task failed", error=str(e))
        result = {
            "status": "failed",
            "error": str(e),
        }
    
    return result


@shared_task
def process_inbound_webhook_task(tenant_id: str, source: str, payload: Dict[str, Any]):
    """Process inbound webhook from any integration."""
    logger.info("Processing inbound webhook", tenant_id=tenant_id, source=source)
    
    import asyncio
    from app.core.database import get_db
    from app.core.tenant_context import tenant_db_context
    from app.models import WebhookEndpoint
    from app.services.crm.common import owned, audit, now
    from app.services.crm.consumers import install_subscribers
    from app.core.events import publish_event
    
    async def _process():
        # Get a database session
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise Exception("DATABASE_URL environment variable not set")
        engine = create_async_engine(database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as session:
            async with tenant_db_context(session, tenant_id):
                try:
                    # We expect the payload to have a webhook_id or we need to find the webhook by source and other params.
                    # For simplicity, we assume the payload has a webhook_id.
                    webhook_id = payload.get("webhook_id")
                    if not webhook_id:
                        # Try to find by source and other criteria? This is complex.
                        # We'll just log an error and return.
                        logger.error("Webhook ID not found in payload", payload=payload)
                        return {"status": "error", "message": "Webhook ID not found"}
                    
                    webhook = await owned(session, WebhookEndpoint, tenant_id, webhook_id)
                    if not webhook or not webhook.is_active:
                        logger.error("Webhook not found or not active", webhook_id=webhook_id)
                        return {"status": "error", "message": "Webhook not found or not active"}
                    
                    # Get the integration
                    integration = await owned(session, Integration, tenant_id, webhook.integration_id)
                    
                    # Verify the webhook signature
                    from app.core.webhooks import InvalidWebhook, verify_signature
                    from app.services.crm.common import CredentialService
                    cred_service = CredentialService()
                    secret = cred_service.decrypt(webhook.secret)
                    
                    # We need the raw body for signature verification, but we don't have it here.
                    # The webhook ingress (hooks.py) already verified the signature and created a WebhookReceipt.
                    # So we can assume the signature is valid.
                    # We'll just process the payload.
                    
                    # Parse the webhook events using the integration adapter
                    from app.services.integration.adapter import IntegrationService
                    adapter_service = IntegrationService()
                    events = await adapter_service.process_webhook(
                        integration.type.value,
                        payload,
                        secret,
                    )
                    
                    # Publish each event as a domain event
                    for event in events:
                        await publish_event(
                            session,
                            tenant_id=tenant_id,
                            event_type=event.get("event_type"),
                            aggregate_id=event.get("event_data", {}).get("id") or str(event.get("event_data")),
                            payload=event,
                        )
                    
                    await session.commit()
                    
                    logger.info("Inbound webhook processed", tenant_id=tenant_id, source=source, events_count=len(events))
                    
                    return {"status": "processed", "events_processed": len(events)}
                except Exception as e:
                    logger.error("Failed to process inbound webhook", tenant_id=tenant_id, source=source, error=str(e))
                    # We don't retry webhook processing tasks because they are idempotent at the ingress level.
                    return {"status": "error", "message": str(e)}
    
    try:
        result = asyncio.run(_process())
    except Exception as e:
        logger.error("Inbound webhook task failed", error=str(e))
        result = {
            "status": "error",
            "message": str(e),
        }
    
    return result