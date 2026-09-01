"""
Campaign Celery tasks for Globexa CRM.
"""
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone, timedelta
from uuid import UUID
import structlog
import asyncio

from app.core.database import AsyncSessionLocal
from app.models import (
    Campaign, CampaignRecipient, CampaignSequence, CampaignTemplate,
    CampaignStats, Contact, SendingDomain, Activity, ActivityTypeEnum,
    CampaignStatusEnum, CampaignRecipientStatusEnum, CampaignTypeEnum
)
from app.services.email.provider import EmailService, EmailMessage, EmailProviderType, ProviderConfig

logger = structlog.get_logger()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_campaign_task(self, campaign_id: str, user_id: str):
    """Main task to send a campaign (broadcast or sequence)."""
    logger.info("Sending campaign", campaign_id=campaign_id)
    
    async def _send():
        async with AsyncSessionLocal() as db:
            # Load campaign with all relations
            result = await db.execute(
                select(Campaign)
                .where(Campaign.id == UUID(campaign_id))
                .options(
                    selectinload(Campaign.audience),
                    selectinload(Campaign.templates),
                    selectinload(Campaign.sequences),
                    selectinload(Campaign.sending_domain),
                )
            )
            campaign = result.scalar_one_or_none()
            if not campaign:
                logger.error("Campaign not found", campaign_id=campaign_id)
                return

            # Create recipients if not exist
            await _create_recipients(db, campaign)
            
            if campaign.type == CampaignTypeEnum.BROADCAST:
                await _send_broadcast(db, campaign)
            elif campaign.type == CampaignTypeEnum.SEQUENCE:
                await _send_sequence_step(db, campaign, 0)  # Start with first step
            elif campaign.type == CampaignTypeEnum.TRIGGERED:
                # Triggered campaigns are event-driven, not sent directly
                logger.info("Triggered campaign - not sent directly", campaign_id=campaign_id)
                return

            # Update campaign status
            campaign.status = CampaignStatusEnum.SENT
            campaign.sent_at = datetime.now(timezone.utc)
            campaign.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
            # Update stats
            await _update_campaign_stats(db, campaign)
            
            logger.info("Campaign sent", campaign_id=campaign_id, type=campaign.type.value)

    asyncio.run(_send())


async def _create_recipients(db: AsyncSession, campaign: Campaign):
    """Create recipient records from audience."""
    if not campaign.audience:
        return

    audience = campaign.audience
    contact_ids = []

    if audience.type.value == "static":
        contact_ids = audience.contact_ids
    else:
        # Dynamic audience - query based on filters
        query = select(Contact.id).where(Contact.tenant_id == campaign.tenant_id)
        filters = audience.filters or {}
        
        if "status" in filters and filters["status"]:
            query = query.where(Contact.lead_status.in_(filters["status"]))
        if "source" in filters:
            query = query.where(Contact.source == filters["source"])
        if "tags" in filters and filters["tags"]:
            query = query.where(Contact.tags.overlap(filters["tags"]))
        
        # Exclude suppressed
        if audience.exclude_suppressed:
            # Add suppression exclusion logic
            pass
        
        result = await db.execute(query)
        contact_ids = [str(r[0]) for r in result.fetchall()]

    # Remove excluded contacts
    exclude_ids = set(audience.exclude_contact_ids)
    contact_ids = [cid for cid in contact_ids if cid not in exclude_ids]

    # Create recipient records
    existing_result = await db.execute(
        select(CampaignRecipient.contact_id).where(
            CampaignRecipient.campaign_id == campaign.id,
            CampaignRecipient.contact_id.in_(contact_ids)
        )
    )
    existing_ids = set(str(r[0]) for r in existing_result.fetchall())
    
    new_contact_ids = [cid for cid in contact_ids if cid not in existing_ids]
    
    if not new_contact_ids:
        return

    # Get contact details
    contacts_result = await db.execute(
        select(Contact).where(Contact.id.in_(new_contact_ids))
    )
    contacts = {str(c.id): c for c in contacts_result.scalars().all()}

    # Get template for broadcast (first template)
    template = None
    if campaign.templates:
        template = campaign.templates[0]

    recipients = []
    for contact_id in new_contact_ids:
        contact = contacts.get(contact_id)
        if not contact or not contact.email:
            continue
        
        # Check suppression
        if audience.exclude_suppressed or audience.exclude_unsubscribed or audience.exclude_bounced:
            # Check suppression list
            from app.models import SuppressionList
            suppression = await db.execute(
                select(SuppressionList).where(
                    SuppressionList.tenant_id == campaign.tenant_id,
                    SuppressionList.email == contact.email,
                    SuppressionList.is_active == True,
                )
            )
            if suppression.scalar_one_or_none():
                continue

        recipient = CampaignRecipient(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            template_id=template.id if template else None,
            contact_id=UUID(contact_id),
            email=contact.email,
            status=CampaignRecipientStatusEnum.QUEUED,
            queued_at=datetime.now(timezone.utc),
            idempotency_key=f"{campaign.id}:{contact_id}",
        )
        recipients.append(recipient)

    if recipients:
        db.add_all(recipients)
        await db.commit()
        logger.info("Created recipients", count=len(recipients), campaign_id=str(campaign.id))


async def _send_broadcast(db: AsyncSession, campaign: Campaign):
    """Send broadcast campaign to all recipients."""
    # Get queued recipients
    result = await db.execute(
        select(CampaignRecipient)
        .where(
            CampaignRecipient.campaign_id == campaign.id,
            CampaignRecipient.status == CampaignRecipientStatusEnum.QUEUED,
        )
        .options(selectinload(CampaignRecipient.contact))
        .limit(500)  # Batch size
    )
    recipients = result.scalars().all()

    if not recipients:
        return

    # Get sending domain config
    provider_type, provider_config = await _get_provider_config(db, campaign)
    if not provider_config:
        logger.error("No provider config for campaign", campaign_id=str(campaign.id))
        campaign.status = CampaignStatusEnum.FAILED
        await db.commit()
        return

    # Get template
    template = campaign.templates[0] if campaign.templates else None
    if not template:
        logger.error("No template for broadcast", campaign_id=str(campaign.id))
        return

    # Send emails
    email_service = EmailService()
    sent_count = 0
    failed_count = 0

    for recipient in recipients:
        # AI personalization
        html_content = template.html_content
        text_content = template.text_content
        
        if campaign.ai_personalization_enabled and recipient.contact:
            # Call AI to personalize
            personalized = await _personalize_content(
                template.html_content,
                template.text_content,
                recipient.contact,
                campaign.ai_personalization_prompt,
            )
            if personalized:
                html_content = personalized.get("html", html_content)
                text_content = personalized.get("text", text_content)
                recipient.ai_personalized = True
                recipient.ai_personalization_data = personalized

        message = EmailMessage(
            to=[recipient.email],
            subject=template.subject,
            html_content=html_content,
            text_content=text_content,
            from_email=campaign.sender_email,
            from_name=campaign.sender_name,
            reply_to=campaign.reply_to_email,
            track_opens=campaign.track_opens,
            track_clicks=campaign.track_clicks,
        )

        result = await email_service.send_email(message, provider_type, provider_config)
        
        if result.success:
            recipient.status = CampaignRecipientStatusEnum.SENT
            recipient.sent_at = datetime.now(timezone.utc)
            recipient.provider_message_id = result.message_id
            recipient.provider_type = provider_type
            sent_count += 1
            
            # Create activity
            activity = Activity(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                lead_id=None,
                contact_id=recipient.contact_id,
                type=ActivityTypeEnum.CAMPAIGN_SENT,
                subject=f"Campaign sent: {campaign.name}",
                description=f"Email sent to {recipient.email}",
                user_id=UUID(campaign.created_by_id),
                is_ai_generated=recipient.ai_personalized,
            )
            db.add(activity)
        else:
            recipient.status = CampaignRecipientStatusEnum.FAILED
            recipient.error_message = result.error_message
            failed_count += 1

        await db.commit()

        # Throttle
        await asyncio.sleep(0.1)

    logger.info("Broadcast sent", campaign_id=str(campaign.id), sent=sent_count, failed=failed_count)


async def _send_sequence_step(db: AsyncSession, campaign: Campaign, step_order: int):
    """Send a specific sequence step."""
    # Get sequence step
    result = await db.execute(
        select(CampaignSequence)
        .where(
            CampaignSequence.campaign_id == campaign.id,
            CampaignSequence.step_order == step_order,
        )
        .options(selectinload(CampaignSequence.template))
    )
    sequence = result.scalar_one_or_none()
    if not sequence:
        # No more steps - campaign complete
        campaign.status = CampaignStatusEnum.COMPLETED
        campaign.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return

    # Get recipients for this step (those who completed previous step)
    if step_order == 0:
        # First step - all queued recipients
        result = await db.execute(
            select(CampaignRecipient)
            .where(
                CampaignRecipient.campaign_id == campaign.id,
                CampaignRecipient.status == CampaignRecipientStatusEnum.QUEUED,
            )
            .options(selectinload(CampaignRecipient.contact))
        )
    else:
        # Subsequent steps - recipients who had previous step delivered
        prev_result = await db.execute(
            select(CampaignRecipient.id).where(
                CampaignRecipient.campaign_id == campaign.id,
                CampaignRecipient.status.in_([
                    CampaignRecipientStatusEnum.DELIVERED,
                    CampaignRecipientStatusEnum.OPENED,
                    CampaignRecipientStatusEnum.CLICKED,
                    CampaignRecipientStatusEnum.REPLIED,
                ]),
            )
        )
        prev_ids = [r[0] for r in prev_result.fetchall()]
        
        result = await db.execute(
            select(CampaignRecipient)
            .where(
                CampaignRecipient.campaign_id == campaign.id,
                CampaignRecipient.status == CampaignRecipientStatusEnum.QUEUED,
            )
            .options(selectinload(CampaignRecipient.contact))
        )
    recipients = result.scalars().all()

    if not recipients:
        # Schedule next step check
        return

    # Get provider config
    provider_type, provider_config = await _get_provider_config(db, campaign)
    if not provider_config:
        return

    template = sequence.template
    if not template:
        return

    email_service = EmailService()

    for recipient in recipients:
        # Check stop conditions
        if sequence.stop_on_reply:
            # Check if contact replied
            pass
        
        # AI personalization
        html_content = template.html_content
        text_content = template.text_content
        
        if campaign.ai_personalization_enabled and recipient.contact:
            personalized = await _personalize_content(
                template.html_content,
                template.text_content,
                recipient.contact,
                campaign.ai_personalization_prompt,
            )
            if personalized:
                html_content = personalized.get("html", html_content)
                text_content = personalized.get("text", text_content)
                recipient.ai_personalized = True

        message = EmailMessage(
            to=[recipient.email],
            subject=template.subject,
            html_content=html_content,
            text_content=text_content,
            from_email=campaign.sender_email,
            from_name=campaign.sender_name,
            reply_to=campaign.reply_to_email,
            track_opens=campaign.track_opens,
            track_clicks=campaign.track_clicks,
        )

        result = await email_service.send_email(message, provider_type, provider_config)
        
        if result.success:
            recipient.status = CampaignRecipientStatusEnum.SENT
            recipient.sent_at = datetime.now(timezone.utc)
            recipient.provider_message_id = result.message_id
            recipient.provider_type = provider_type
        else:
            recipient.status = CampaignRecipientStatusEnum.FAILED
            recipient.error_message = result.error_message

        await db.commit()
        await asyncio.sleep(0.1)

    # Schedule next step
    next_step_order = step_order + 1
    delay = timedelta(days=sequence.delay_days, hours=sequence.delay_hours)
    # In production, use Celery beat or schedule next task
    # For now, just log
    logger.info("Sequence step sent, next step scheduled", 
                campaign_id=str(campaign.id), 
                next_step=next_step_order)


async def _get_provider_config(db: AsyncSession, campaign: Campaign):
    """Get email provider configuration for campaign."""
    if campaign.sending_domain_id:
        result = await db.execute(
            select(SendingDomain).where(SendingDomain.id == campaign.sending_domain_id)
        )
        domain = result.scalar_one_or_none()
        if domain and domain.provider_config:
            provider_type = EmailProviderType(domain.provider)
            # Decrypt credentials (simplified)
            config = ProviderConfig(
                provider_type=provider_type,
                credentials=domain.provider_config,
            )
            return provider_type, config

    # Fallback to tenant default provider config
    from app.models import EmailProviderConfig
    result = await db.execute(
        select(EmailProviderConfig).where(
            EmailProviderConfig.tenant_id == campaign.tenant_id,
            EmailProviderConfig.is_default == True,
            EmailProviderConfig.is_active == True,
        )
    )
    config_obj = result.scalar_one_or_none()
    if config_obj:
        provider_type = EmailProviderType(config_obj.provider)
        # Decrypt credentials
        import json
        from cryptography.fernet import Fernet
        # Simplified - in production use proper encryption
        credentials = json.loads(config_obj.credentials_encrypted)
        config = ProviderConfig(
            provider_type=provider_type,
            credentials=credentials,
        )
        return provider_type, config

    return None, None


async def _personalize_content(html_content: str, text_content: str, contact: Contact, prompt: str = None):
    """Call AI to personalize email content."""
    if not prompt:
        prompt = "Personalize this email for the recipient using their name, company, and role."

    from app.services.ai.router import get_ai_router
    router = get_ai_router()

    personalization_prompt = f"""
    {prompt}
    
    Recipient:
    - Name: {contact.full_name}
    - Company: {contact.company.name if contact.company else 'N/A'}
    - Title: {contact.title or 'N/A'}
    - Industry: {contact.company.industry if contact.company else 'N/A'}
    
    Original HTML:
    {html_content}
    
    Original Text:
    {text_content or 'N/A'}
    
    Return JSON: {{"html": "...", "text": "..."}}
    """

    result = await router.complete(
        task_type="personalization",
        prompt=personalization_prompt,
        tenant_id=contact.tenant_id,
        user_id=contact.created_by_id,
        response_format={"type": "json_object"},
    )

    if result.success:
        import json
        try:
            return json.loads(result.content)
        except json.JSONDecodeError:
            return None
    return None


async def _update_campaign_stats(db: AsyncSession, campaign: Campaign):
    """Update campaign statistics."""
    result = await db.execute(
        select(CampaignStats).where(CampaignStats.campaign_id == campaign.id)
    )
    stats = result.scalar_one_or_none()
    if not stats:
        stats = CampaignStats(tenant_id=campaign.tenant_id, campaign_id=campaign.id)
        db.add(stats)

    # Compute stats from recipients
    recipient_result = await db.execute(
        select(
            CampaignRecipient.status,
            func.count().label("count"),
        )
        .where(CampaignRecipient.campaign_id == campaign.id)
        .group_by(CampaignRecipient.status)
    )
    status_counts = {row[0].value: row[1] for row in recipient_result.fetchall()}

    stats.total_recipients = sum(status_counts.values())
    stats.queued = status_counts.get("queued", 0)
    stats.sent = status_counts.get("sent", 0)
    stats.delivered = status_counts.get("delivered", 0)
    stats.failed = status_counts.get("failed", 0)
    stats.bounced = status_counts.get("bounced", 0)
    stats.suppressed = status_counts.get("suppressed", 0)

    # Engagement counts would come from webhook processing
    # For now, just compute rates
    if stats.sent > 0:
        stats.delivery_rate = stats.delivered / stats.sent
    if stats.delivered > 0:
        stats.open_rate = stats.opened / stats.delivered
        stats.click_rate = stats.clicked / stats.delivered
        stats.reply_rate = stats.replied / stats.delivered
        stats.bounce_rate = stats.bounced / stats.sent
        stats.unsubscribe_rate = stats.unsubscribed / stats.sent

    stats.last_calculated_at = datetime.now(timezone.utc)
    await db.commit()


# =============================================================================
# Webhook Processing Tasks
# =============================================================================

@shared_task
def process_email_webhook(tenant_id: str, provider: str, payload: dict):
    """Process email provider webhook."""
    logger.info("Processing email webhook", tenant_id=tenant_id, provider=provider)
    
    async def _process():
        async with AsyncSessionLocal() as db:
            provider_type = EmailProviderType(provider)
            email_service = EmailService()
            
            # Get provider config
            from app.models import EmailProviderConfig
            result = await db.execute(
                select(EmailProviderConfig).where(
                    EmailProviderConfig.tenant_id == UUID(tenant_id),
                    EmailProviderConfig.provider == provider_type,
                    EmailProviderConfig.is_active == True,
                )
            )
            config_obj = result.scalar_one_or_none()
            if not config_obj:
                logger.error("No provider config for webhook", tenant_id=tenant_id, provider=provider)
                return

            import json
            credentials = json.loads(config_obj.credentials_encrypted)
            config = ProviderConfig(
                provider_type=provider_type,
                credentials=credentials,
            )

            # Parse events
            events = await email_service.process_webhook(provider_type, payload, config)
            
            for event in events:
                await _process_email_event(db, UUID(tenant_id), event)

            await db.commit()

    asyncio.run(_process())


async def _process_email_event(db: AsyncSession, tenant_id: UUID, event: dict):
    """Process a single email event."""
    provider_event_id = event.get("provider_event_id")
    event_type = event.get("provider_event_type")
    recipient_email = event.get("recipient_email")
    provider_message_id = event.get("provider_message_id")

    if not provider_event_id:
        return

    # Store raw event
    from app.models import EmailEvent
    email_event = EmailEvent(
        tenant_id=tenant_id,
        provider=event.get("provider", "unknown"),
        provider_event_id=provider_event_id,
        provider_event_type=event_type,
        recipient_id=None,
        provider_message_id=provider_message_id,
        event_data=event.get("event_data", {}),
        event_timestamp=datetime.now(timezone.utc),
    )
    db.add(email_event)

    # Find recipient
    recipient = None
    if provider_message_id:
        result = await db.execute(
            select(CampaignRecipient).where(
                CampaignRecipient.provider_message_id == provider_message_id,
                CampaignRecipient.tenant_id == tenant_id,
            )
        )
        recipient = result.scalar_one_or_none()

    if not recipient and recipient_email:
        result = await db.execute(
            select(CampaignRecipient).where(
                CampaignRecipient.email == recipient_email,
                CampaignRecipient.tenant_id == tenant_id,
            ).order_by(CampaignRecipient.created_at.desc())
        )
        recipient = result.scalar_one_or_none()

    if recipient:
        email_event.recipient_id = recipient.id
        
        # Update recipient status based on event
        if event_type in ["delivered", "delivered"]:
            recipient.status = CampaignRecipientStatusEnum.DELIVERED
            recipient.delivered_at = datetime.now(timezone.utc)
        elif event_type in ["opened", "open"]:
            recipient.status = CampaignRecipientStatusEnum.OPENED
            recipient.open_count += 1
            if not recipient.first_opened_at:
                recipient.first_opened_at = datetime.now(timezone.utc)
            recipient.last_opened_at = datetime.now(timezone.utc)
        elif event_type in ["clicked", "click"]:
            recipient.status = CampaignRecipientStatusEnum.CLICKED
            recipient.click_count += 1
            if not recipient.first_clicked_at:
                recipient.first_clicked_at = datetime.now(timezone.utc)
            recipient.last_clicked_at = datetime.now(timezone.utc)
        elif event_type in ["replied", "reply"]:
            recipient.status = CampaignRecipientStatusEnum.REPLIED
            recipient.replied_at = datetime.now(timezone.utc)
        elif event_type in ["bounced", "bounce"]:
            recipient.status = CampaignRecipientStatusEnum.BOUNCED
            recipient.bounced_at = datetime.now(timezone.utc)
            recipient.bounce_type = event.get("event_data", {}).get("bounce_type", "unknown")
            recipient.bounce_reason = event.get("event_data", {}).get("bounce_reason", "")
            
            # Add to suppression list
            from app.models import SuppressionList
            suppression = SuppressionList(
                tenant_id=tenant_id,
                email=recipient.email,
                contact_id=recipient.contact_id,
                reason="bounced",
                reason_detail=recipient.bounce_reason,
                provider=recipient.provider_type,
                provider_event_id=provider_event_id,
            )
            db.add(suppression)
        elif event_type in ["complained", "complaint", "spam"]:
            recipient.status = CampaignRecipientStatusEnum.COMPLAINED
            recipient.complained_at = datetime.now(timezone.utc)
            
            # Add to suppression list
            from app.models import SuppressionList
            suppression = SuppressionList(
                tenant_id=tenant_id,
                email=recipient.email,
                contact_id=recipient.contact_id,
                reason="complained",
                provider=recipient.provider_type,
                provider_event_id=provider_event_id,
            )
            db.add(suppression)
        elif event_type in ["unsubscribed", "unsubscribe"]:
            recipient.status = CampaignRecipientStatusEnum.UNSUBSCRIBED
            recipient.unsubscribed_at = datetime.now(timezone.utc)
            
            # Add to suppression list
            from app.models import SuppressionList
            suppression = SuppressionList(
                tenant_id=tenant_id,
                email=recipient.email,
                contact_id=recipient.contact_id,
                reason="unsubscribed",
                provider=recipient.provider_type,
                provider_event_id=provider_event_id,
            )
            db.add(suppression)

        # Create activity
        activity = Activity(
            tenant_id=tenant_id,
            campaign_id=recipient.campaign_id,
            lead_id=None,
            contact_id=recipient.contact_id,
            type=_event_type_to_activity(event_type),
            subject=f"Email {event_type}: {recipient.campaign.name if recipient.campaign else 'Campaign'}",
            description=f"Email {event_type} for {recipient.email}",
            is_ai_generated=False,
        )
        db.add(activity)

    await db.commit()


def _event_type_to_activity(event_type: str) -> ActivityTypeEnum:
    """Map provider event type to activity type."""
    mapping = {
        "delivered": ActivityTypeEnum.EMAIL_DELIVERED,
        "opened": ActivityTypeEnum.EMAIL_OPENED,
        "clicked": ActivityTypeEnum.EMAIL_CLICKED,
        "replied": ActivityTypeEnum.EMAIL_REPLIED,
        "bounced": ActivityTypeEnum.EMAIL_BOUNCED,
        "complained": ActivityTypeEnum.EMAIL_COMPLAINED,
        "unsubscribed": ActivityTypeEnum.EMAIL_UNSUBSCRIBED,
    }
    return mapping.get(event_type, ActivityTypeEnum.EMAIL)


# =============================================================================
# Scheduled Tasks
# =============================================================================

@shared_task
def process_scheduled_campaigns():
    """Check and send scheduled campaigns."""
    logger.info("Processing scheduled campaigns")
    
    # Use synchronous execution instead of asyncio.run() to avoid event loop conflicts
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        # Schedule the coroutine to run in the existing loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, _process())
            return future.result()
    else:
        asyncio.run(_process())


async def _process():
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Campaign).where(
                Campaign.status == CampaignStatusEnum.SCHEDULED,
                Campaign.scheduled_at <= now,
            )
        )
        campaigns = result.scalars().all()

        for campaign in campaigns:
            send_campaign_task.delay(str(campaign.id), str(campaign.created_by_id))


@shared_task
def retry_failed_emails():
    """Retry failed email sends."""
    logger.info("Retrying failed emails")
    
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, _retry())
            return future.result()
    else:
        asyncio.run(_retry())


async def _retry():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CampaignRecipient).where(
                CampaignRecipient.status == CampaignRecipientStatusEnum.FAILED,
            ).limit(100)
        )
        recipients = result.scalars().all()

        for recipient in recipients:
            recipient.status = CampaignRecipientStatusEnum.QUEUED
            recipient.error_message = None
            
            # Re-queue
            send_campaign_task.delay(str(recipient.campaign_id), str(recipient.campaign.created_by_id))

        await db.commit()


@shared_task
def aggregate_campaign_stats():
    """Aggregate campaign statistics."""
    logger.info("Aggregating campaign stats")
    
    async def _aggregate():
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Campaign).where(Campaign.status.in_([
                CampaignStatusEnum.SENDING,
                CampaignStatusEnum.SENT,
                CampaignStatusEnum.COMPLETED,
            ])))
            campaigns = result.scalars().all()

            for campaign in campaigns:
                await _update_campaign_stats(db, campaign)

    asyncio.run(_aggregate())