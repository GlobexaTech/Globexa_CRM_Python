"""Transactional outbox: persist alongside CRM mutations, deliver at least once."""
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

EVENT_TYPES = frozenset({"lead.created", "lead.updated", "contact.created", "deal.created",
                         "campaign.started", "message.received", "integration.synced"})


class Publisher(Protocol):
    async def publish(self, event_id: str, tenant_id: str) -> None: ...


class Subscriber(Protocol):
    name: str
    event_types: set[str]

    async def handle(self, db, domain_event) -> None: ...


class CeleryPublisher:
    async def publish(self, event_id, tenant_id):
        from app.workers.tasks.foundation_tasks import deliver_event
        deliver_event.delay(tenant_id=tenant_id, event_id=event_id)


def publish_event(db, *, tenant_id, event_type, aggregate_id, actor_id=None,
                  payload=None, idempotency_key=None):
    from app.models import DomainEvent
    if event_type not in EVENT_TYPES:
        raise ValueError("Unregistered domain event")
    item = DomainEvent(id=uuid4(), tenant_id=tenant_id, event_type=event_type,
                       aggregate_id=str(aggregate_id), actor_id=actor_id,
                       payload=payload or {}, idempotency_key=idempotency_key or str(uuid4()))
    db.add(item)
    return item


async def drain_outbox(db, publisher: Publisher, limit=100):
    from app.models import DomainEvent
    items = (await db.scalars(select(DomainEvent).where(DomainEvent.published_at.is_(None))
                             .order_by(DomainEvent.created_at).limit(limit)
                             .with_for_update(skip_locked=True))).all()
    for item in items:
        await publisher.publish(str(item.id), str(item.tenant_id))
        item.published_at = datetime.now(timezone.utc)
    await db.flush()
    return len(items)


subscribers: dict[str, Subscriber] = {}


def register_subscriber(subscriber: Subscriber):
    if subscriber.name in subscribers:
        raise ValueError("Duplicate subscriber")
    if not subscriber.event_types <= EVENT_TYPES:
        raise ValueError("Unregistered event subscription")
    subscribers[subscriber.name] = subscriber


async def dispatch_event(db, event_id):
    from app.models import DomainEvent, EventDelivery
    # Serialize same-event deliveries; subscriber effects and receipt commit atomically.
    item = await db.scalar(select(DomainEvent).where(DomainEvent.id == event_id).with_for_update())
    if item is None:
        raise ValueError("Event not found in tenant")
    for subscriber in subscribers.values():
        if item.event_type not in subscriber.event_types:
            continue
        receipt = await db.scalar(select(EventDelivery).where(
            EventDelivery.event_id == item.id, EventDelivery.subscriber == subscriber.name))
        if receipt and receipt.completed_at:
            continue
        await subscriber.handle(db, item)
        db.add(EventDelivery(tenant_id=item.tenant_id, event_id=item.id,
                             subscriber=subscriber.name, completed_at=datetime.now(timezone.utc)))
    await db.flush()


@event.listens_for(Session, "before_flush")
def capture_changes(db, flush_context, instances):
    """Only identifiers enter audit/outbox records; credentials and prompts never do."""
    from app.models import (Lead, Contact, Deal, Campaign, Message, Integration,
                            IntegrationSyncLog, IntegrationCredential, OAuthToken,
                            WebhookEndpoint, Membership, AuditLog, AIUsageLog)
    from app.core.tenant_context import current_user
    create_events = {Lead: "lead.created", Contact: "contact.created", Deal: "deal.created",
                     Message: "message.received"}
    audited = {Campaign, Integration, IntegrationCredential, OAuthToken, WebhookEndpoint,
               Membership, AIUsageLog, IntegrationSyncLog}
    for obj in list(db.new) + list(db.dirty) + list(db.deleted):
        if type(obj) is AuditLog:
            from app.core.input_security import redact
            obj.old_values = redact(obj.old_values)
            obj.new_values = redact(obj.new_values)
            continue
        new = obj in db.new
        deleted = obj in db.deleted
        if not new and not deleted and not db.is_modified(obj, include_collections=False):
            continue
        if not getattr(obj, "tenant_id", None):
            continue
        if new and getattr(obj, "id", None) is None:
            obj.id = uuid4()
        actor = db.info.get("security_context", (None, current_user.get()))[1]
        name = create_events.get(type(obj)) if new else None
        if isinstance(obj, Lead) and not new and not deleted:
            name = "lead.updated"
        if isinstance(obj, Campaign) and inspect(obj).attrs.status.history.has_changes():
            if getattr(obj.status, "value", obj.status) == "sending":
                name = "campaign.started"
        if isinstance(obj, Integration) and inspect(obj).attrs.last_sync_status.history.has_changes():
            if getattr(obj.last_sync_status, "value", obj.last_sync_status) == "completed":
                name = "integration.synced"
        if name and not deleted:
            publish_event(db, tenant_id=obj.tenant_id, event_type=name,
                          aggregate_id=obj.id, actor_id=actor)
        if type(obj) in audited:
            action = "created" if new else "deleted" if deleted else "updated"
            if not new and not deleted and type(obj) in {IntegrationCredential, OAuthToken}:
                action = "rotated"
            db.add(AuditLog(tenant_id=obj.tenant_id, user_id=actor,
                            action=f"{obj.__tablename__}.{action}",
                            resource_type=obj.__tablename__, resource_id=str(obj.id), success=True))
