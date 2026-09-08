"""Public webhook ingress; an endpoint identifier grants no tenant authority."""
import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.credentials import CredentialService
from app.core.tenant_context import bind_context, tenant_db_context
from app.core.webhooks import InvalidWebhook, verify_signature
from app.core.events import publish_event
from app.models import AuditLog, WebhookReceipt, WebhookEndpoint

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
        async with tenant_db_context(route["tenant_id"]) as audit_db:
            audit_db.add(AuditLog(tenant_id=route["tenant_id"], action="webhook.failed",
                                  resource_type="webhook", resource_id=str(endpoint_id), success=False))
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
    from app.core.input_security import redact
    item = publish_event(db, tenant_id=route["tenant_id"], event_type="message.received",
                         aggregate_id=endpoint_id, payload={"webhook_id": str(endpoint_id), "body": redact(payload)},
                         idempotency_key=f"webhook:{endpoint_id}:{digest}")
    await db.flush()
    db.add(WebhookReceipt(tenant_id=route["tenant_id"], webhook_id=endpoint_id,
                          digest=digest, event_id=item.id))
    await db.commit()
    return {"status": "accepted", "event_id": str(item.id)}
