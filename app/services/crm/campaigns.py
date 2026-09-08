"""Campaign lifecycle and durable per-recipient, per-step delivery intents."""

from datetime import timedelta
import hashlib
from uuid import UUID
from sqlalchemy import select, func, delete
from fastapi import HTTPException
from app.models import (
    Campaign,
    CampaignAudience,
    CampaignTemplate,
    CampaignSequence,
    CampaignRecipient,
    CampaignStats,
    CampaignStatusEnum,
    CampaignRecipientStatusEnum,
    CampaignTypeEnum,
    AudienceTypeEnum,
    Contact,
    Integration,
    OperationJob,
    CampaignTrigger,
    TriggerTypeEnum,
)
from app.services.crm.common import owned, authorize, meter, enqueue, audit, now
from app.services.crm.conversations import suppressed
from app.services.crm.providers import adapter_for
from app.services.crm.unsubscribe import unsubscribe_url


async def configure_campaign(db, tenant_id, actor_id, campaign_id, data):
    await authorize(db, tenant_id, actor_id, "campaigns:write")
    campaign = await owned(db, Campaign, tenant_id, campaign_id, True)
    if campaign.status != CampaignStatusEnum.DRAFT:
        raise HTTPException(409, "Only draft campaign content can be changed")
    integration = await owned(db, Integration, tenant_id, data.integration_id)
    if "send" not in adapter_for(integration).capabilities:
        raise HTTPException(501, "Provider cannot send")
    query = select(Contact).where(Contact.tenant_id == tenant_id)
    if data.contact_ids:
        query = query.where(Contact.id.in_(data.contact_ids))
    elif data.company_id:
        query = query.where(Contact.company_id == data.company_id)
    else:
        raise HTTPException(422, "Select contacts or a company audience")
    contacts = (await db.scalars(query.order_by(Contact.id).limit(1001))).all()
    if len(contacts) > 1000:
        raise HTTPException(422, "Audience exceeds 1000 contacts; split the campaign")
    if data.contact_ids and {r.id for r in contacts} != set(data.contact_ids):
        raise HTTPException(404, "Recipient outside this tenant")
    audience = await db.scalar(
        select(CampaignAudience).where(
            CampaignAudience.tenant_id == tenant_id,
            CampaignAudience.campaign_id == campaign_id,
        )
    )
    if audience is None:
        audience = CampaignAudience(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            name=campaign.name,
            type=AudienceTypeEnum.STATIC,
        )
        db.add(audience)
    audience.contact_ids = [str(c.id) for c in contacts]
    audience.estimated_count = len(contacts)
    campaign.custom_fields = {
        **(campaign.custom_fields or {}),
        "delivery_integration_id": str(integration.id),
    }
    for model in (CampaignTrigger, CampaignSequence, CampaignTemplate):
        await db.execute(
            delete(model).where(
                model.tenant_id == tenant_id, model.campaign_id == campaign_id
            )
        )
    steps = [
        {"subject": data.subject, "body": data.body, "delay_hours": 0}
    ] + data.steps
    total_delay = 0
    for index, step in enumerate(steps):
        if (
            set(step) - {"subject", "body", "delay_hours"}
            or not isinstance(step.get("subject"), str)
            or not isinstance(step.get("body"), str)
        ):
            raise HTTPException(422, "Invalid sequence content")
        delay = step.get("delay_hours", 24)
        if (
            not isinstance(delay, int)
            or not 0 <= delay <= 720
            or len(step["subject"]) > 500
            or len(step["body"]) > 100000
        ):
            raise HTTPException(422, "Invalid sequence delay or content length")
        total_delay += delay
        template = CampaignTemplate(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            name=f"Step {index + 1}",
            step_order=index,
            subject=step["subject"],
            text_content=step["body"],
            html_content="",
        )
        db.add(template)
        await db.flush()
        db.add(
            CampaignSequence(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                step_order=index,
                template_id=template.id,
                delay_days=total_delay // 24,
                delay_hours=total_delay % 24,
                send_on_weekends=True,
            )
        )
    campaign.type = (
        CampaignTypeEnum.SEQUENCE if len(steps) > 1 else CampaignTypeEnum.BROADCAST
    )
    if data.trigger_event:
        if data.steps:
            raise HTTPException(
                422, "Triggered campaigns support one template per trigger"
            )
        campaign.type = CampaignTypeEnum.TRIGGERED
        db.add(
            CampaignTrigger(
                tenant_id=tenant_id,
                campaign_id=campaign.id,
                name=data.trigger_event,
                trigger_type=TriggerTypeEnum.CUSTOM_EVENT,
                template_id=template.id,
                conditions={"event_type": data.trigger_event},
            )
        )
    audit(db, tenant_id, actor_id, "campaign.configured", "campaign", campaign_id)
    return {"id": campaign.id, "contacts": len(contacts), "steps": len(steps)}


async def transition(
    db, tenant_id, actor_id, campaign_id, operation, scheduled_at=None
):
    await authorize(db, tenant_id, actor_id, "campaigns:send")
    campaign = await owned(db, Campaign, tenant_id, campaign_id, True)
    status = campaign.status.value
    if operation == "schedule":
        if scheduled_at is not None and scheduled_at.tzinfo is None:
            raise HTTPException(422, "Schedule must include a timezone")
        if status != "draft" or scheduled_at is None or scheduled_at <= now():
            raise HTTPException(409, "Schedule requires a draft and a future timestamp")
        if not (campaign.custom_fields or {}).get("delivery_integration_id"):
            raise HTTPException(409, "Configure campaign delivery first")
        campaign.scheduled_at, campaign.status = (
            scheduled_at,
            CampaignStatusEnum.SCHEDULED,
        )
    elif operation in {"launch", "resume"}:
        if status == "sending":
            return {"id": campaign.id, "status": "running"}
        allowed = {"draft", "scheduled"} if operation == "launch" else {"paused"}
        if status not in allowed:
            raise HTTPException(409, "Invalid campaign transition")
        if (
            operation == "resume"
            and not campaign.sent_at
            and campaign.scheduled_at
            and campaign.scheduled_at > now()
        ):
            campaign.status = CampaignStatusEnum.SCHEDULED
            audit(db, tenant_id, actor_id, "campaign.resume", "campaign", campaign.id)
            return {"id": campaign.id, "status": "scheduled"}
        if operation == "launch" or not campaign.sent_at:
            await meter(db, tenant_id, actor_id, "campaigns")
            if campaign.type != CampaignTypeEnum.TRIGGERED:
                await enroll(db, tenant_id, actor_id, campaign)
        campaign.status = CampaignStatusEnum.SENDING
        campaign.sent_at = campaign.sent_at or now()
    elif operation == "pause":
        if status not in {"sending", "scheduled", "paused"}:
            raise HTTPException(
                409, "Only running or scheduled campaigns can be paused"
            )
        campaign.status = CampaignStatusEnum.PAUSED
    elif operation == "cancel":
        if status == "completed":
            raise HTTPException(409, "Completed campaign cannot be cancelled")
        campaign.status = CampaignStatusEnum.CANCELLED
    else:
        raise HTTPException(422, "Unknown transition")
    audit(db, tenant_id, actor_id, "campaign." + operation, "campaign", campaign_id)
    await db.flush()
    return {
        "id": campaign.id,
        "status": "running"
        if campaign.status.value == "sending"
        else campaign.status.value,
    }


async def enroll(db, tenant_id, actor_id, campaign):
    integration_id = (campaign.custom_fields or {}).get("delivery_integration_id")
    if not integration_id:
        raise HTTPException(409, "Configure campaign delivery first")
    integration = await owned(db, Integration, tenant_id, UUID(integration_id))
    if "send" not in adapter_for(integration).capabilities:
        raise HTTPException(501, "Provider sending unavailable")
    audience = await db.scalar(
        select(CampaignAudience).where(
            CampaignAudience.tenant_id == tenant_id,
            CampaignAudience.campaign_id == campaign.id,
        )
    )
    templates = (
        await db.scalars(
            select(CampaignTemplate)
            .where(
                CampaignTemplate.tenant_id == tenant_id,
                CampaignTemplate.campaign_id == campaign.id,
            )
            .order_by(CampaignTemplate.step_order)
        )
    ).all()
    steps = (
        await db.scalars(
            select(CampaignSequence)
            .where(
                CampaignSequence.tenant_id == tenant_id,
                CampaignSequence.campaign_id == campaign.id,
            )
            .order_by(CampaignSequence.step_order)
        )
    ).all()
    if (
        not audience
        or not templates
        or not audience.contact_ids
        or len(audience.contact_ids) > 1000
    ):
        raise HTTPException(409, "Campaign needs bounded recipients and content")
    seen = set()
    base = now()
    for contact_id in audience.contact_ids:
        contact = await owned(db, Contact, tenant_id, UUID(str(contact_id)))
        if not contact.email or contact.email.lower() in seen:
            continue
        seen.add(contact.email.lower())
        blocked = await suppressed(db, tenant_id, contact.email, contact)
        for index, template in enumerate(templates):
            email_key = hashlib.sha256(contact.email.lower().encode()).hexdigest()
            key = f"campaign:{campaign.id}:{email_key}:{index}"
            step = next((s for s in steps if s.template_id == template.id), None)
            available = (
                base + timedelta(days=step.delay_days, hours=step.delay_hours)
                if step
                else base
            )
            recipient = CampaignRecipient(
                tenant_id=tenant_id,
                campaign_id=campaign.id,
                contact_id=contact.id,
                template_id=template.id,
                email=contact.email,
                status=CampaignRecipientStatusEnum.SUPPRESSED
                if blocked
                else CampaignRecipientStatusEnum.QUEUED,
                queued_at=base,
                scheduled_at=available,
                idempotency_key=key,
            )
            db.add(recipient)
            await db.flush()
            if not blocked:
                opt_out = unsubscribe_url(tenant_id, contact.id)
                await enqueue(
                    db,
                    tenant_id,
                    actor_id,
                    "campaign_send",
                    key,
                    {
                        "campaign_id": str(campaign.id),
                        "recipient_id": str(recipient.id),
                        "integration_id": integration_id,
                        "recipient": contact.email,
                        "subject": template.subject,
                        "body": (template.text_content or "")
                        + "\n\nUnsubscribe: "
                        + opt_out,
                        "unsubscribe_url": opt_out,
                        "step": index,
                    },
                    available_at=available,
                )
    await update_stats(db, tenant_id, campaign.id)


async def update_stats(db, tenant_id, campaign_id):
    await db.flush()
    counts = dict(
        (status.value, count)
        for status, count in (
            await db.execute(
                select(CampaignRecipient.status, func.count())
                .where(
                    CampaignRecipient.tenant_id == tenant_id,
                    CampaignRecipient.campaign_id == campaign_id,
                )
                .group_by(CampaignRecipient.status)
            )
        ).all()
    )
    stats = await db.scalar(
        select(CampaignStats).where(
            CampaignStats.tenant_id == tenant_id,
            CampaignStats.campaign_id == campaign_id,
        )
    )
    if not stats:
        stats = CampaignStats(tenant_id=tenant_id, campaign_id=campaign_id)
        db.add(stats)
    stats.total_recipients = sum(counts.values())
    stats.sent = sum(
        counts.get(s, 0) for s in ("sent", "delivered", "opened", "clicked", "replied")
    )
    for name in (
        "queued",
        "delivered",
        "failed",
        "bounced",
        "suppressed",
        "opened",
        "clicked",
        "replied",
        "unsubscribed",
        "complained",
    ):
        setattr(stats, name, counts.get(name, 0))
    stats.last_calculated_at = now()
    campaign = await owned(db, Campaign, tenant_id, campaign_id, True)
    pending = await db.scalar(
        select(func.count())
        .select_from(OperationJob)
        .where(
            OperationJob.tenant_id == tenant_id,
            OperationJob.kind == "campaign_send",
            OperationJob.payload["campaign_id"].astext == str(campaign_id),
            OperationJob.status.in_(["pending", "running", "retry", "unknown"]),
        )
    )
    if (
        not pending
        and campaign.status == CampaignStatusEnum.SENDING
        and campaign.type != CampaignTypeEnum.TRIGGERED
    ):
        campaign.status, campaign.completed_at = CampaignStatusEnum.COMPLETED, now()
    await db.flush()
    return {
        "campaign_id": campaign.id,
        "status": "running"
        if campaign.status.value == "sending"
        else campaign.status.value,
        "total_recipients": stats.total_recipients,
        "sent": stats.sent,
        "queued": stats.queued,
        "failed": stats.failed,
        "suppressed": stats.suppressed,
        "opened": stats.opened,
        "replied": stats.replied,
    }


async def trigger_campaigns(db, event):
    contact_id = (
        event.aggregate_id
        if event.event_type == "contact.created"
        else event.payload.get("contact_id")
    )
    if not contact_id:
        return
    triggers = (
        await db.scalars(
            select(CampaignTrigger)
            .join(Campaign, Campaign.id == CampaignTrigger.campaign_id)
            .where(
                CampaignTrigger.tenant_id == event.tenant_id,
                CampaignTrigger.is_active.is_(True),
                CampaignTrigger.conditions["event_type"].astext == event.event_type,
                Campaign.status == CampaignStatusEnum.SENDING,
                Campaign.type == CampaignTypeEnum.TRIGGERED,
            )
        )
    ).all()
    for trigger in triggers:
        campaign = await owned(db, Campaign, event.tenant_id, trigger.campaign_id, True)
        try:
            await authorize(
                db, event.tenant_id, campaign.created_by_id, "campaigns:send"
            )
        except HTTPException:
            audit(
                db,
                event.tenant_id,
                campaign.created_by_id,
                "campaign.trigger_denied",
                "campaign",
                campaign.id,
                False,
            )
            continue
        contact = await owned(db, Contact, event.tenant_id, UUID(contact_id))
        audience = await db.scalar(
            select(CampaignAudience).where(
                CampaignAudience.tenant_id == event.tenant_id,
                CampaignAudience.campaign_id == campaign.id,
            )
        )
        if (
            str(contact.id) not in (audience.contact_ids if audience else [])
            or not contact.email
            or await suppressed(db, event.tenant_id, contact.email, contact)
        ):
            continue
        previous = (
            await db.scalars(
                select(OperationJob).where(
                    OperationJob.tenant_id == event.tenant_id,
                    OperationJob.payload["trigger_id"].astext == str(trigger.id),
                    OperationJob.payload["contact_id"].astext == contact_id,
                )
            )
        ).all()
        if len(previous) >= trigger.max_triggers_per_contact or any(
            j.created_at > now() - timedelta(hours=trigger.cooldown_hours)
            for j in previous
        ):
            continue
        template = await owned(
            db, CampaignTemplate, event.tenant_id, trigger.template_id
        )
        key = f"trigger:{trigger.id}:{contact.id}:{event.id}"
        opt_out = unsubscribe_url(event.tenant_id, contact.id)
        recipient = CampaignRecipient(
            tenant_id=event.tenant_id,
            campaign_id=campaign.id,
            template_id=template.id,
            contact_id=contact.id,
            email=contact.email,
            idempotency_key=key,
            status=CampaignRecipientStatusEnum.QUEUED,
            queued_at=now(),
        )
        db.add(recipient)
        await db.flush()
        await enqueue(
            db,
            event.tenant_id,
            campaign.created_by_id,
            "campaign_send",
            key,
            {
                "campaign_id": str(campaign.id),
                "recipient_id": str(recipient.id),
                "integration_id": campaign.custom_fields["delivery_integration_id"],
                "recipient": contact.email,
                "subject": template.subject,
                "body": (template.text_content or "") + "\n\nUnsubscribe: " + opt_out,
                "unsubscribe_url": opt_out,
                "step": 0,
                "trigger_id": str(trigger.id),
                "contact_id": contact_id,
            },
            available_at=now() + timedelta(minutes=trigger.delay_minutes),
        )
