"""Persistent, idempotent subscribers; each receipt commits with its effects."""

from uuid import UUID
from sqlalchemy import select
from app.core.events import EVENT_TYPES, subscribers, register_subscriber
from app.models import (
    AnalyticsEvent,
    Message,
    Conversation,
    WebhookEndpoint,
    Integration,
    UsageRecord,
    OperationJob,
    CampaignRecipient,
    CampaignRecipientStatusEnum,
    Contact,
)
from app.services.crm.common import owned, enqueue, now


class AnalyticsSubscriber:
    name = "crm.analytics.v1"
    event_types = set(EVENT_TYPES)

    async def handle(self, db, event):
        db.add(
            AnalyticsEvent(
                tenant_id=event.tenant_id,
                event_id=event.id,
                event_type=event.event_type,
                entity_id=event.aggregate_id,
                value=event.payload.get("value"),
                dimensions={
                    k: v
                    for k, v in event.payload.items()
                    if k not in {"body", "_depth"}
                },
            )
        )
        if event.event_type == "campaign.completed":
            db.add(
                UsageRecord(
                    tenant_id=event.tenant_id,
                    user_id=event.actor_id,
                    metric="campaigns_completed",
                    quantity=1,
                    period_start=now(),
                    period_end=now(),
                )
            )


class CRMSubscriber:
    name = "crm.operations.v1"
    event_types = set(EVENT_TYPES)

    async def handle(self, db, event):
        from app.services.crm.automation import trigger_workflows

        if "webhook_id" in event.payload:
            endpoint = await owned(
                db, WebhookEndpoint, event.tenant_id, UUID(event.payload["webhook_id"])
            )
            integration = await owned(
                db, Integration, event.tenant_id, endpoint.integration_id
            )
            from app.services.crm.providers import adapter_for

            adapter = adapter_for(integration)
            # Signed ingress is preserved. Provider notifications request a sync, never trust caller tenant IDs.
            if "sync" in adapter.capabilities and integration.created_by_id:
                await enqueue(
                    db,
                    event.tenant_id,
                    integration.created_by_id,
                    "sync",
                    "webhook-sync:" + str(event.id),
                    {"integration_id": str(integration.id), "cursor": None},
                )
            return
        if event.event_type == "message.received":
            message = await owned(
                db, Message, event.tenant_id, UUID(event.aggregate_id)
            )
            conversation = await owned(
                db, Conversation, event.tenant_id, message.conversation_id, True
            )
            conversation.unread_count += 1
            if (
                not conversation.last_message_at
                or message.occurred_at > conversation.last_message_at
            ):
                conversation.last_message_at = message.occurred_at
            outbound = (
                await db.scalars(
                    select(Message)
                    .where(
                        Message.tenant_id == event.tenant_id,
                        Message.conversation_id == conversation.id,
                        Message.direction == "outbound",
                        Message.idempotency_key.like("job:%"),
                    )
                    .limit(20)
                )
            ).all()
            for previous in outbound:
                operation = await db.scalar(
                    select(OperationJob).where(
                        OperationJob.tenant_id == event.tenant_id,
                        OperationJob.id == UUID(previous.idempotency_key[4:]),
                        OperationJob.kind == "campaign_send",
                    )
                )
                if operation:
                    recipient = await owned(
                        db,
                        CampaignRecipient,
                        event.tenant_id,
                        UUID(operation.payload["recipient_id"]),
                    )
                    recipient.replied_at, recipient.status = (
                        message.occurred_at,
                        CampaignRecipientStatusEnum.REPLIED,
                    )
            if conversation.contact_id and message.body.strip().lower() in {
                "unsubscribe",
                "stop",
                "remove me",
                "do not contact",
            }:
                contact = await owned(
                    db, Contact, event.tenant_id, conversation.contact_id
                )
                contact.email_opted_out = True
        elif event.event_type == "message.sent":
            message = await owned(
                db, Message, event.tenant_id, UUID(event.aggregate_id)
            )
            conversation = await owned(
                db, Conversation, event.tenant_id, message.conversation_id, True
            )
            conversation.last_message_at = max(
                conversation.last_message_at or message.occurred_at, message.occurred_at
            )
        await trigger_workflows(db, event)
        from app.services.crm.campaigns import trigger_campaigns

        await trigger_campaigns(db, event)
        capability = {
            "lead.created": "lead_score",
            "deal.stage_changed": "next_best_action",
            "message.received": "reply_analysis",
        }.get(event.event_type)
        if capability:
            # Hooks prepare controlled suggestions; no autonomous model call or spend.
            await enqueue(
                db,
                event.tenant_id,
                event.actor_id,
                "ai_hook",
                "ai-hook:" + str(event.id),
                {"capability": capability, "entity_id": event.aggregate_id},
                status="awaiting_approval",
            )


def install_subscribers():
    for consumer in (AnalyticsSubscriber(), CRMSubscriber()):
        if consumer.name not in subscribers:
            register_subscriber(consumer)
