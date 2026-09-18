"""Durable provider normalization and persistence. Tenant authority is never payload data."""
from uuid import UUID
from sqlalchemy import select, func, or_
from app.models import (Contact, Lead, Message, Conversation, Integration, SyncJob, SyncCursor,
                        WebhookReceipt, WebhookEndpoint, DeadLetterEvent, IntegrationSyncLog, SyncStatusEnum)
from app.services.crm.common import owned, serial_key, now
from app.services.crm.providers import adapter_for, ProviderFailure


async def match_contact(db, tenant_id, integration_id, identity, relationship_id=None):
    """Provider identity > verified email > verified phone > verified relationship.

    An ambiguous identity never falls through to a weaker match. Names are never
    identifiers. Customer-editable arbitrary fields cannot claim verification:
    provider identifiers are resolved only through server-owned conversation relationships.
    """
    provider_id = identity.get("provider_contact_id") or identity.get("provider_id")
    conditions = []
    if provider_id:
        trusted = select(Conversation.contact_id).where(Conversation.tenant_id == tenant_id,
            Conversation.integration_id == integration_id, Conversation.provider_thread_id == str(provider_id),
            Conversation.contact_id.is_not(None))
        conditions.append(Contact.id.in_(trusted))
    if identity.get("email_verified") and identity.get("email"):
        conditions.append(func.lower(Contact.email) == identity["email"].lower())
    if identity.get("phone_verified") and identity.get("phone"):
        import re
        number = re.sub(r"[^0-9]", "", identity["phone"])
        conditions.append(or_(func.regexp_replace(Contact.phone, r"[^0-9]", "", "g") == number,
                              func.regexp_replace(Contact.mobile, r"[^0-9]", "", "g") == number))
    if relationship_id:
        conditions.append(Contact.id == relationship_id)
    for condition in conditions:
        matches = (await db.scalars(select(Contact).where(Contact.tenant_id == tenant_id, condition).limit(2))).all()
        if matches:
            return {"status": "MATCHED" if len(matches) == 1 else "AMBIGUOUS",
                    "contact": matches[0] if len(matches) == 1 else None,
                    "candidate_ids": [str(row.id) for row in matches]}
    return {"status": "NEW", "contact": None, "candidate_ids": []}



async def ingest_lead(db, tenant_id, integration, item):
    provider_id = str(item["provider_id"])
    key = f"{integration.id}:{provider_id}"
    await serial_key(db, tenant_id, "lead-provider:" + key)
    existing = await db.scalar(select(Lead).where(Lead.tenant_id == tenant_id, Lead.source_id == key))
    if existing:
        return existing, False
    if len(key) > 255:
        raise ProviderFailure("provider_id_too_long")
    match = await match_contact(db, tenant_id, integration.id, item)
    contact = match["contact"]
    if match["status"] == "NEW":
        contact = Contact(tenant_id=tenant_id, first_name=str(item.get("first_name") or "New")[:100],
                          last_name=str(item.get("last_name") or "Lead")[:100], email=item.get("email"), phone=item.get("phone"),
                          created_by_id=integration.created_by_id,
                          custom_fields={"provider_identities": [{"integration_id": str(integration.id), "provider_id": provider_id}],
                                         "provenance": {"provider": item.get("provider"), "retrieved_at": now().isoformat()}})
        db.add(contact)
        await db.flush()
    lead = Lead(tenant_id=tenant_id, contact_id=contact.id if contact else None,
                title=(str(item.get("first_name") or "New") + " " + str(item.get("last_name") or "Lead"))[:255],
                source_id=key, created_by_id=integration.created_by_id,
                custom_fields={"provider": item.get("provider"), "provider_id": provider_id,
                               "integration_id": str(integration.id), "match_status": match["status"],
                               "review_required": match["status"] == "AMBIGUOUS"})
    db.add(lead)
    await db.flush()
    return lead, True


async def execute_sync_page(db, tenant_id, job, integration, adapter, token):
    """One atomic page. Cursor commits with normalized CRM data, never before it."""
    from app.services.crm.conversations import ingest_message
    await serial_key(db, tenant_id, "sync:" + str(integration.id))
    sync_id = (job.result or {}).get("sync_job_id")
    sync = await owned(db, SyncJob, tenant_id, UUID(sync_id), True) if sync_id else None
    if sync is None:
        sync = SyncJob(tenant_id=tenant_id, integration_id=integration.id, sync_type="incremental", status="running")
        db.add(sync)
        await db.flush()
    if sync.status == "cancelled":
        return {"cancelled": True, "sync_job_id": str(sync.id), "records_processed": sync.records_processed}
    sync.status, sync.started_at = "running", sync.started_at or now()
    cursor = await db.scalar(select(SyncCursor).where(SyncCursor.tenant_id == tenant_id,
                            SyncCursor.integration_id == integration.id, SyncCursor.cursor_type == "provider").with_for_update())
    result = await adapter.sync(token, cursor.cursor_value if cursor else None)
    messages, leads = result.get("messages", []), result.get("leads", [])
    if len(messages) + len(leads) > 1000:
        raise ProviderFailure("provider_page_too_large")
    for item in messages:
        await ingest_message(db, tenant_id, integration, item)
    for item in leads:
        await ingest_lead(db, tenant_id, integration, item)
    count = len(messages) + len(leads)
    await db.flush()
    value = result.get("cursor")
    if value is not None and (not isinstance(value, str) or len(value) > 16000):
        raise ProviderFailure("invalid_provider_cursor")
    if value is not None:
        if cursor:
            cursor.cursor_value = value
        else:
            db.add(SyncCursor(tenant_id=tenant_id, integration_id=integration.id, cursor_type="provider", cursor_value=value))
    elif cursor:
        await db.delete(cursor)
    more = bool(result.get("has_more", False))
    sync.status = "partial" if more else "completed"
    sync.cursor = value
    sync.records_processed += count
    sync.finished_at = None if more else now()
    integration.last_sync_at = now()
    integration.last_sync_status = SyncStatusEnum.PARTIAL if more else SyncStatusEnum.COMPLETED
    integration.last_sync_error = None
    integration.records_synced += count
    db.add(IntegrationSyncLog(tenant_id=tenant_id, integration_id=integration.id, sync_type="incremental",
                              status=integration.last_sync_status, records_processed=count, started_at=sync.started_at, completed_at=now()))
    return {"sync_job_id": str(sync.id), "records_processed": sync.records_processed, "has_more": more, "metered": True}


async def apply_delivery_status(db, tenant_id, integration_id, event):
    message = await db.scalar(select(Message).join(Conversation, Conversation.id == Message.conversation_id).where(
        Message.tenant_id == tenant_id, Conversation.integration_id == integration_id,
        Message.provider_message_id == event["provider_message_id"], Message.direction == "outbound").with_for_update())
    if message is None:
        raise ProviderFailure("outbound_message_not_persisted_yet", retryable=True, retry_after=5)
    rank = {"queued": 0, "sending": 1, "unknown": 1, "sent": 2, "failed": 2, "delivered": 3, "read": 4}
    status = event["status"]
    if rank.get(status, -1) > rank.get(message.status, -1) or (status == "failed" and message.status in {"queued", "sending", "sent", "unknown"}):
        message.status = status
    return message


async def process_receipt(db, tenant_id, receipt_id):
    """Claim and normalize inside an RLS transaction; retry failures remain durable."""
    from app.services.crm.conversations import ingest_message
    from app.services.crm.integrations import access_token
    receipt = await owned(db, WebhookReceipt, tenant_id, receipt_id, True)
    if receipt.state in {"completed", "dead_letter"}:
        return {"state": receipt.state}
    endpoint = await owned(db, WebhookEndpoint, tenant_id, receipt.webhook_id)
    integration = await owned(db, Integration, tenant_id, endpoint.integration_id)
    adapter = adapter_for(integration)
    receipt.state = "processing"
    receipt.attempts += 1
    try:
        async with db.begin_nested():
            events = await adapter.handle_webhook(receipt.payload)
            for event in events:
                configured_account = (integration.config or {}).get("phone_number_id" if adapter.name == "whatsapp" else "form_id" if adapter.name == "google_ads" else "page_id")
                if not configured_account or str(configured_account) != event.get("account_id"):
                    raise ProviderFailure("webhook_account_mismatch")
                await serial_key(db, tenant_id, f"provider-event:{integration.id}:{event['provider_event_id']}")
                if event["kind"] == "message":
                    await ingest_message(db, tenant_id, integration, event["message"])
                elif event["kind"] == "status":
                    await apply_delivery_status(db, tenant_id, integration.id, event)
                elif event["kind"] == "lead_reference":
                    token = await access_token(db, tenant_id, integration)
                    await ingest_lead(db, tenant_id, integration, await adapter.fetch_lead(token, event["lead_id"]))
                elif event["kind"] == "lead":
                    await ingest_lead(db, tenant_id, integration, event["lead"])
                else:
                    raise ProviderFailure("unsupported_webhook_event")
            await db.flush()
        receipt.state, receipt.error_code, receipt.processed_at = "completed", None, now()
        # Raw payload retention ends after successful normalization.
        receipt.payload = {}
    except (ProviderFailure, ValueError, KeyError, TypeError) as exc:
        code = exc.code if isinstance(exc, ProviderFailure) else "invalid_provider_payload"
        retry = isinstance(exc, ProviderFailure) and exc.retryable and receipt.attempts < min(endpoint.max_retries, 5)
        receipt.state, receipt.error_code = ("failed" if retry else "dead_letter"), code
        if not retry:
            db.add(DeadLetterEvent(tenant_id=tenant_id, provider=adapter.name, event_type="webhook",
                                   provider_event_id=str(receipt.id), payload={"receipt_id": str(receipt.id)},
                                   error_message=code, retry_count=receipt.attempts))
            receipt.payload = {}
    await db.flush()
    return {"state": receipt.state, "receipt_id": str(receipt.id)}
