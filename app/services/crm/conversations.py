from datetime import datetime
from sqlalchemy import select, func
from fastapi import HTTPException
from app.models import (
    Conversation,
    Message,
    Participant,
    Contact,
    Company,
    Lead,
    Integration,
    SuppressionList,
)
from app.services.crm.common import owned, authorize, meter, audit, enqueue, serial_key


async def create_conversation(db, tenant_id, actor_id, data):
    await authorize(db, tenant_id, actor_id, "conversations:write")
    for field, model in {
        "contact_id": Contact,
        "company_id": Company,
        "lead_id": Lead,
        "integration_id": Integration,
    }.items():
        value = getattr(data, field)
        if value:
            await owned(db, model, tenant_id, value)
    row = Conversation(tenant_id=tenant_id, **data.model_dump(exclude={"participants"}))
    db.add(row)
    await db.flush()
    for person in {p.address: p for p in data.participants}.values():
        db.add(
            Participant(
                tenant_id=tenant_id, conversation_id=row.id, **person.model_dump()
            )
        )
    audit(db, tenant_id, actor_id, "conversation.created", "conversation", row.id)
    return row


async def suppressed(db, tenant_id, email, contact=None):
    if contact and (contact.email_opted_out or contact.do_not_contact):
        return True
    # Also honor preferences when the caller has no explicit contact relationship.
    blocked_contact = await db.scalar(
        select(Contact.id)
        .where(
            Contact.tenant_id == tenant_id,
            func.lower(Contact.email) == email.lower(),
            (Contact.email_opted_out.is_(True) | Contact.do_not_contact.is_(True)),
        )
        .limit(1)
    )
    blocked = await db.scalar(
        select(SuppressionList.id)
        .where(
            SuppressionList.tenant_id == tenant_id,
            func.lower(SuppressionList.email) == email.lower(),
            SuppressionList.is_active.is_(True),
        )
        .limit(1)
    )
    return bool(blocked or blocked_contact)


async def queue_message(db, tenant_id, actor_id, conversation_id, data, key):
    await authorize(db, tenant_id, actor_id, "conversations:send")
    row = await owned(db, Conversation, tenant_id, conversation_id, True)
    if row.channel != "email" or not row.integration_id:
        raise HTTPException(
            501, "Configure a supported email integration before sending"
        )
    if data.attachments:
        raise HTTPException(
            422,
            "Only attachment metadata ingestion is supported; outbound attachment upload is unavailable",
        )
    if await suppressed(db, tenant_id, str(data.recipient)):
        raise HTTPException(409, "Recipient is suppressed or unsubscribed")
    payload = {
        "conversation_id": str(row.id),
        "integration_id": str(row.integration_id),
        "recipient": str(data.recipient),
        "subject": row.subject,
        "body": data.body,
        "thread_id": row.provider_thread_id,
    }
    job, created = await enqueue(
        db, tenant_id, actor_id, "message_send", "message:" + key, payload
    )
    if created:
        await meter(db, tenant_id, actor_id, "messages")
        db.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=row.id,
                body=data.body,
                direction="outbound",
                status="queued",
                recipient=str(data.recipient),
                idempotency_key="job:" + str(job.id),
            )
        )
        audit(db, tenant_id, actor_id, "message.queued", "conversation", row.id)
    return job


async def ingest_message(db, tenant_id, integration, item):
    from app.schemas.operations import Attachment
    from pydantic import TypeAdapter

    if not item.get("provider_message_id") or not item.get("thread_id"):
        raise ValueError("Provider message/thread identity required")
    key = f"provider:{integration.id}:{item['provider_message_id']}"
    if len(key) > 255 or len(item.get("body", "")) > 100000:
        raise ValueError("Provider message exceeds contract")
    await serial_key(
        db, tenant_id, "thread:" + str(integration.id) + ":" + item["thread_id"]
    )
    existing = await db.scalar(
        select(Message).where(
            Message.tenant_id == tenant_id, Message.idempotency_key == key
        )
    )
    if existing:
        return existing
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.integration_id == integration.id,
            Conversation.provider_thread_id == item["thread_id"],
        )
    )
    contact = await db.scalar(
        select(Contact)
        .where(
            Contact.tenant_id == tenant_id,
            func.lower(Contact.email) == item.get("sender", "").lower(),
        )
        .order_by(Contact.id)
        .limit(1)
    )
    if not conversation:
        conversation = Conversation(
            tenant_id=tenant_id,
            integration_id=integration.id,
            provider_thread_id=item["thread_id"],
            subject=item.get("subject", "(no subject)")[:255],
            contact_id=contact.id if contact else None,
            company_id=contact.company_id if contact else None,
        )
        db.add(conversation)
        await db.flush()
    stamp = datetime.fromisoformat(item["occurred_at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Provider timestamp must include timezone")
    attachments = TypeAdapter(list[Attachment]).validate_python(
        item.get("attachments", [])
    )
    if len(attachments) > 10:
        raise ValueError("Too many attachments")
    total_bytes = sum(a.size for a in attachments)
    if total_bytes:
        await meter(db, tenant_id, integration.created_by_id, "storage", total_bytes)
    message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        body=item.get("body") or "(empty message)",
        direction="inbound",
        status="received",
        sender=item.get("sender"),
        recipient=item.get("recipient"),
        provider_message_id=item["provider_message_id"],
        idempotency_key=key,
        occurred_at=stamp,
        attachments=[a.model_dump() for a in attachments],
    )
    db.add(message)
    await db.flush()
    for address in {item.get("sender"), item.get("recipient")} - {None, ""}:
        person = await db.scalar(
            select(Participant).where(
                Participant.tenant_id == tenant_id,
                Participant.conversation_id == conversation.id,
                Participant.address == address,
            )
        )
        if not person:
            db.add(
                Participant(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    address=address,
                )
            )
    return message
