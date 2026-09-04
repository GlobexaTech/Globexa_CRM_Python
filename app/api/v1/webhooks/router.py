"""Webhook endpoints for integration events."""
from typing import Optional, Dict, Any, List
from uuid import UUID
from fastapi import APIRouter, Request, Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import json

from app.core.database import get_db
from app.core.webhook_security import (
    verify_webhook,
    WebhookProvider,
    WebhookVerificationResult,
)
from app.services.integration.service import IntegrationService
from app.models import WebhookEndpoint, Integration

logger = structlog.get_logger()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/meta/leadgen")
async def meta_leadgen_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    db: AsyncSession = Depends(get_db),
):
    """Meta (Facebook/Instagram) Lead Gen webhook endpoint."""
    # Get raw body
    body = await request.body()
    
    # Get webhook secret from the endpoint config
    # The path contains the webhook identifier
    path = request.url.path
    
    # Find webhook endpoint
    integration_service = IntegrationService(db)
    
    # For Meta, we need to find the webhook by the path
    result = await db.execute(
        "SELECT we.*, i.type FROM webhook_endpoints we "
        "JOIN integrations i ON we.integration_id = i.id "
        "WHERE we.url_path = :path AND we.is_active = true",
        {"path": path}
    )
    webhook = result.first()
    
    if not webhook:
        logger.warning("Meta webhook: endpoint not found", path=path)
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    
    # Decrypt secret
    secret = await integration_service.get_webhook_secret(webhook.id, webhook.tenant_id)
    if not secret:
        logger.error("Meta webhook: failed to decrypt secret")
        raise HTTPException(status_code=500, detail="Internal error")
    
    # Verify webhook
    verification = await verify_webhook(
        provider=WebhookProvider.META,
        payload=body,
        headers={"X-Hub-Signature-256": x_hub_signature_256 or ""},
        secret=secret,
    )
    
    if not verification.valid:
        logger.warning("Meta webhook verification failed", 
                      error=verification.error,
                      path=path)
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Process events
    payload = verification.payload
    events_processed = 0
    
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == "leadgen":
                value = change.get("value", {})
                leadgen_id = value.get("leadgen_id")
                form_id = value.get("form_id")
                page_id = entry.get("id")
                
                # Process the lead
                # This would typically queue a background task
                logger.info("Meta lead received",
                           leadgen_id=leadgen_id,
                           form_id=form_id,
                           page_id=page_id)
                events_processed += 1
    
    return {
        "status": "ok",
        "events_processed": events_processed,
    }


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    db: AsyncSession = Depends(get_db),
):
    """WhatsApp Business API webhook endpoint."""
    body = await request.body()
    
    path = request.url.path
    integration_service = IntegrationService(db)
    
    result = await db.execute(
        "SELECT we.*, i.type FROM webhook_endpoints we "
        "JOIN integrations i ON we.integration_id = i.id "
        "WHERE we.url_path = :path AND we.is_active = true",
        {"path": path}
    )
    webhook = result.first()
    
    if not webhook:
        logger.warning("WhatsApp webhook: endpoint not found", path=path)
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    
    secret = await integration_service.get_webhook_secret(webhook.id, webhook.tenant_id)
    if not secret:
        raise HTTPException(status_code=500, detail="Internal error")
    
    verification = await verify_webhook(
        provider=WebhookProvider.WHATSAPP,
        payload=body,
        headers={"X-Hub-Signature-256": x_hub_signature_256 or ""},
        secret=secret,
    )
    
    if not verification.valid:
        logger.warning("WhatsApp webhook verification failed", error=verification.error)
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Process WhatsApp events
    payload = verification.payload
    
    # Handle WhatsApp message status updates, incoming messages, etc.
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            logger.info("WhatsApp event received", event=change.get("field"))
    
    return {"status": "ok"}


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Stripe webhook endpoint."""
    body = await request.body()
    
    path = request.url.path
    integration_service = IntegrationService(db)
    
    result = await db.execute(
        "SELECT we.*, i.type FROM webhook_endpoints we "
        "JOIN integrations i ON we.integration_id = i.id "
        "WHERE we.url_path = :path AND we.is_active = true",
        {"path": path}
    )
    webhook = result.first()
    
    if not webhook:
        logger.warning("Stripe webhook: endpoint not found", path=path)
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    
    secret = await integration_service.get_webhook_secret(webhook.id, webhook.tenant_id)
    if not secret:
        raise HTTPException(status_code=500, detail="Internal error")
    
    verification = await verify_webhook(
        provider=WebhookProvider.STRIPE,
        payload=body,
        headers={"Stripe-Signature": stripe_signature or ""},
        secret=secret,
    )
    
    if not verification.valid:
        logger.warning("Stripe webhook verification failed", error=verification.error)
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Process Stripe events
    event = verification.payload
    logger.info("Stripe event received", event_type=event.get("type"), event_id=event.get("id"))
    
    # Handle different event types
    # e.g., payment_intent.succeeded, customer.subscription.updated, etc.
    
    return {"status": "ok"}


@router.post("/generic/{webhook_id}")
async def generic_webhook(
    webhook_id: UUID,
    request: Request,
    x_webhook_signature: Optional[str] = Header(None, alias="X-Webhook-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Generic webhook endpoint for custom integrations."""
    body = await request.body()
    
    integration_service = IntegrationService(db)
    
    result = await db.execute(
        "SELECT we.*, i.type FROM webhook_endpoints we "
        "JOIN integrations i ON we.integration_id = i.id "
        "WHERE we.id = :webhook_id AND we.is_active = true",
        {"webhook_id": str(webhook_id)}
    )
    webhook = result.first()
    
    if not webhook:
        logger.warning("Generic webhook: endpoint not found", webhook_id=str(webhook_id))
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    
    secret = await integration_service.get_webhook_secret(webhook.id, webhook.tenant_id)
    if not secret:
        raise HTTPException(status_code=500, detail="Internal error")
    
    verification = await verify_webhook(
        provider=WebhookProvider.GENERIC,
        payload=body,
        headers={"X-Webhook-Signature": x_webhook_signature or ""},
        secret=secret,
    )
    
    if not verification.valid:
        logger.warning("Generic webhook verification failed", 
                      error=verification.error,
                      webhook_id=str(webhook_id))
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Process generic webhook
    logger.info("Generic webhook received", 
                webhook_id=str(webhook_id),
                event_id=verification.event_id)
    
    return {
        "status": "ok",
        "event_id": verification.event_id,
    }


# Webhook verification endpoint (for provider challenge/verification)
@router.get("/meta/leadgen")
async def meta_webhook_verify(
    request: Request,
    hub_mode: Optional[str] = None,
    hub_challenge: Optional[str] = None,
    hub_verify_token: Optional[str] = None,
):
    """Meta webhook verification endpoint (GET challenge)."""
    # Verify token from config
    # This would be stored in the webhook endpoint config
    verify_token = "your_verify_token"  # Should come from webhook config
    
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        return int(hub_challenge)
    
    raise HTTPException(status_code=403, detail="Verification failed")


@router.get("/whatsapp")
async def whatsapp_webhook_verify(
    request: Request,
    hub_mode: Optional[str] = None,
    hub_challenge: Optional[str] = None,
    hub_verify_token: Optional[str] = None,
):
    """WhatsApp webhook verification endpoint."""
    verify_token = "your_verify_token"  # Should come from webhook config
    
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        return int(hub_challenge)
    
    raise HTTPException(status_code=403, detail="Verification failed")