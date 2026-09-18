"""Public webhook ingress; an endpoint identifier grants no tenant authority."""
import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.credentials import CredentialService
from app.core.tenant_context import bind_context
from app.core.webhooks import InvalidWebhook, verify_signature
from app.core.events import publish_event
from app.models import AuditLog, WebhookReceipt, WebhookEndpoint, Integration

router = APIRouter(prefix="/hooks", tags=["Webhook ingress"])


@router.post("/{endpoint_id}", status_code=202)
async def receive_webhook(endpoint_id: UUID, request: Request, db: AsyncSession = Depends(get_db)):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 1_048_576:
            raise HTTPException(413, "Webhook too large")
    route = (await db.execute(text("SELECT * FROM public.lookup_webhook(:id)"),
                              {"id": endpoint_id})).mappings().one_or_none()
    if not route:
        raise HTTPException(404, "Webhook not found")
    try:
        digest = verify_signature(route["provider"], CredentialService().decrypt(route["secret"]),
                                  bytes(body), request.headers)
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise InvalidWebhook("Object payload required")
    except (InvalidWebhook, ValueError):
        # Record the failed verification in the same request transaction. This is
        # a fixed audit write, not permission to read or mutate tenant CRM data.
        await bind_context(db, route["tenant_id"])
        db.add(AuditLog(tenant_id=route["tenant_id"], action="webhook.failed",
                        resource_type="webhook", resource_id=str(endpoint_id), success=False))
        await db.commit()
        raise HTTPException(401, "Webhook verification failed") from None
    await bind_context(db, route["tenant_id"])
    # The endpoint lock serializes competing retries; receipt and outbox are atomic.
    endpoint = await db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.id == endpoint_id)
                               .with_for_update())
    if not endpoint or not endpoint.is_active:
        raise HTTPException(404, "Webhook not found")
    existing = await db.scalar(select(WebhookReceipt).where(
        WebhookReceipt.webhook_id == endpoint_id, WebhookReceipt.digest == digest))
    if existing:
        return {"status": "duplicate", "event_id": str(existing.event_id)}
    from datetime import timedelta
    from app.services.crm.common import now
    recent = await db.scalar(select(func.count()).select_from(WebhookReceipt).where(
        WebhookReceipt.tenant_id == route["tenant_id"], WebhookReceipt.webhook_id == endpoint_id,
        WebhookReceipt.created_at > now() - timedelta(minutes=1)))
    if recent >= endpoint.rate_limit_per_minute:
        raise HTTPException(429, "Webhook rate limit exceeded", headers={"Retry-After": "60"})
    from app.core.input_security import redact
    from app.services.crm.common import enqueue
    provider = route["provider"]
    provider_pipeline = provider in {"whatsapp", "meta", "instagram", "google_ads"}
    item = publish_event(db, tenant_id=route["tenant_id"],
                         event_type="webhook.received",
                         aggregate_id=endpoint_id, payload={"webhook_id": str(endpoint_id), "receipt_pipeline": provider_pipeline},
                         idempotency_key=f"webhook:{endpoint_id}:{digest}")
    await db.flush()
    # Authentication credentials never enter payload storage.
    payload.pop("google_key", None)
    receipt = WebhookReceipt(tenant_id=route["tenant_id"], webhook_id=endpoint_id,
                             digest=digest, event_id=item.id, payload=redact(payload) if provider_pipeline else {},
                             state="pending" if provider_pipeline else "completed")
    db.add(receipt)
    await db.flush()
    if provider_pipeline:
        integration = await db.scalar(select(Integration).where(Integration.id == endpoint.integration_id))
        if not integration:
            raise HTTPException(404, "Integration not found")
        await enqueue(db, route["tenant_id"], integration.created_by_id, "provider_webhook",
                      "webhook-receipt:" + str(receipt.id), {"receipt_id": str(receipt.id)})
    await db.commit()
    return {"status": "accepted", "event_id": str(item.id), "receipt_id": str(receipt.id)}


@router.get("/{endpoint_id}")
async def verify_subscription(endpoint_id: UUID, request: Request, db: AsyncSession = Depends(get_db)):
    """Meta subscription challenge. Verify-token is distinct from the app signing secret."""
    import hmac
    from fastapi.responses import PlainTextResponse
    route = (await db.execute(text("SELECT * FROM public.lookup_webhook(:id)"), {"id": endpoint_id})).mappings().one_or_none()
    if not route or route["provider"] not in {"meta", "instagram", "whatsapp"}:
        raise HTTPException(404, "Webhook not found")
    await bind_context(db, route["tenant_id"])
    endpoint = await db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.id == endpoint_id))
    expected = (endpoint.custom_fields or {}).get("verify_token_hash", "")
    import hashlib
    supplied = hashlib.sha256(request.query_params.get("hub.verify_token", "").encode()).hexdigest()
    challenge = request.query_params.get("hub.challenge", "")
    if request.query_params.get("hub.mode") != "subscribe" or not expected or not hmac.compare_digest(supplied, expected) or len(challenge) > 2000:
        raise HTTPException(401, "Webhook verification failed")
    return PlainTextResponse(challenge)
