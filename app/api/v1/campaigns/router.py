"""
Campaign API routes for Globexa CRM.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone

from app.core.database import get_db
from app.api.deps import get_current_active_user, require_campaigns_read, require_campaigns_write, require_campaigns_send, get_tenant_id
from app.schemas import PaginationParams, PaginatedResponse
from app.models import (
    Campaign, CampaignAudience, CampaignTemplate, CampaignRecipient,
    CampaignSequence, CampaignTrigger, CampaignStats,
    Contact, SendingDomain, User, CampaignTypeEnum, CampaignStatusEnum,
    CampaignRecipientStatusEnum, AudienceTypeEnum, TriggerTypeEnum
)

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


# =============================================================================
# Campaign CRUD
# =============================================================================

@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    data: dict,
    current_user: tuple = Depends(require_campaigns_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a new campaign."""
    user, _ = current_user

    # Verify sending domain if provided
    if data.get("sending_domain_id"):
        result = await db.execute(
            select(SendingDomain).where(
                SendingDomain.id == data["sending_domain_id"],
                SendingDomain.tenant_id == tenant_id,
                SendingDomain.is_active == True,
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Sending domain not found or inactive")

    campaign = Campaign(
        tenant_id=tenant_id,
        created_by_id=user.id,
        updated_by_id=user.id,
        **data,
    )
    db.add(campaign)
    await db.flush()

    # Create empty audience
    audience = CampaignAudience(
        tenant_id=tenant_id,
        campaign_id=campaign.id,
        name=f"{campaign.name} Audience",
        type=AudienceTypeEnum.STATIC,
    )
    db.add(audience)

    # Create empty stats
    stats = CampaignStats(
        tenant_id=tenant_id,
        campaign_id=campaign.id,
    )
    db.add(stats)

    await db.commit()
    await db.refresh(campaign)
    return {"id": str(campaign.id), "message": "Campaign created"}


@router.get("", response_model=PaginatedResponse)
async def list_campaigns(
    params: PaginationParams = Depends(),
    status: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: tuple = Depends(require_campaigns_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List campaigns with filtering and pagination."""
    query = select(Campaign).where(Campaign.tenant_id == tenant_id).options(
        selectinload(Campaign.stats),
        selectinload(Campaign.audience),
    )

    if status:
        query = query.where(Campaign.status == status)
    if type:
        query = query.where(Campaign.type == type)
    if search:
        query = query.where(
            or_(
                Campaign.name.ilike(f"%{search}%"),
                Campaign.description.ilike(f"%{search}%"),
            )
        )

    query = query.order_by(Campaign.created_at.desc())

    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    campaigns = result.scalars().all()

    return PaginatedResponse.create(
        items=[{
            "id": str(c.id),
            "name": c.name,
            "type": c.type.value,
            "status": c.status.value,
            "scheduled_at": c.scheduled_at,
            "sent_at": c.sent_at,
            "stats": {
                "total": c.stats.total_recipients if c.stats else 0,
                "sent": c.stats.sent if c.stats else 0,
                "delivered": c.stats.delivered if c.stats else 0,
                "opened": c.stats.opened if c.stats else 0,
                "clicked": c.stats.clicked if c.stats else 0,
                "replied": c.stats.replied if c.stats else 0,
            } if c.stats else None,
        } for c in campaigns],
        total=total,
        params=params,
    )


@router.get("/{campaign_id}", response_model=dict)
async def get_campaign(
    campaign_id: UUID,
    current_user: tuple = Depends(require_campaigns_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get a campaign with all related data."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
        .options(
            selectinload(Campaign.audience),
            selectinload(Campaign.templates),
            selectinload(Campaign.sequences),
            selectinload(Campaign.triggers),
            selectinload(Campaign.stats),
            selectinload(Campaign.created_by),
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {
        "id": str(campaign.id),
        "name": campaign.name,
        "description": campaign.description,
        "type": campaign.type.value,
        "status": campaign.status.value,
        "sender_name": campaign.sender_name,
        "sender_email": campaign.sender_email,
        "reply_to_email": campaign.reply_to_email,
        "sending_domain_id": str(campaign.sending_domain_id) if campaign.sending_domain_id else None,
        "scheduled_at": campaign.scheduled_at,
        "sent_at": campaign.sent_at,
        "completed_at": campaign.completed_at,
        "ai_personalization_enabled": campaign.ai_personalization_enabled,
        "ai_personalization_prompt": campaign.ai_personalization_prompt,
        "track_opens": campaign.track_opens,
        "track_clicks": campaign.track_clicks,
        "unsubscribe_enabled": campaign.unsubscribe_enabled,
        "tags": campaign.tags,
        "audience": {
            "type": campaign.audience.type.value if campaign.audience else None,
            "contact_ids": campaign.audience.contact_ids if campaign.audience else [],
            "filters": campaign.audience.filters if campaign.audience else None,
            "estimated_count": campaign.audience.estimated_count if campaign.audience else 0,
        } if campaign.audience else None,
        "templates": [{
            "id": str(t.id),
            "step_order": t.step_order,
            "name": t.name,
            "subject": t.subject,
            "version": t.version,
            "is_active_version": t.is_active_version,
        } for t in campaign.templates],
        "sequences": [{
            "id": str(s.id),
            "step_order": s.step_order,
            "template_id": str(s.template_id),
            "delay_days": s.delay_days,
            "delay_hours": s.delay_hours,
            "send_time": s.send_time,
        } for s in campaign.sequences],
        "triggers": [{
            "id": str(t.id),
            "trigger_type": t.trigger_type.value,
            "name": t.name,
            "template_id": str(t.template_id),
            "delay_minutes": t.delay_minutes,
            "is_active": t.is_active,
        } for t in campaign.triggers],
        "stats": {
            "total_recipients": campaign.stats.total_recipients if campaign.stats else 0,
            "sent": campaign.stats.sent if campaign.stats else 0,
            "delivered": campaign.stats.delivered if campaign.stats else 0,
            "opened": campaign.stats.opened if campaign.stats else 0,
            "clicked": campaign.stats.clicked if campaign.stats else 0,
            "replied": campaign.stats.replied if campaign.stats else 0,
            "bounced": campaign.stats.bounced if campaign.stats else 0,
            "unsubscribed": campaign.stats.unsubscribed if campaign.stats else 0,
            "interested": campaign.stats.interested if campaign.stats else 0,
            "qualified_leads": campaign.stats.qualified_leads if campaign.stats else 0,
            "conversions": campaign.stats.conversions if campaign.stats else 0,
            "revenue": campaign.stats.revenue if campaign.stats else 0,
            "delivery_rate": campaign.stats.delivery_rate if campaign.stats else 0,
            "open_rate": campaign.stats.open_rate if campaign.stats else 0,
            "click_rate": campaign.stats.click_rate if campaign.stats else 0,
            "reply_rate": campaign.stats.reply_rate if campaign.stats else 0,
            "conversion_rate": campaign.stats.conversion_rate if campaign.stats else 0,
        } if campaign.stats else None,
        "created_at": campaign.created_at,
        "updated_at": campaign.updated_at,
    }


@router.patch("/{campaign_id}", response_model=dict)
async def update_campaign(
    campaign_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_campaigns_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a campaign."""
    user, _ = current_user

    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Can't modify sent campaigns
    if campaign.status in [CampaignStatusEnum.SENT, CampaignStatusEnum.COMPLETED]:
        raise HTTPException(status_code=400, detail="Cannot modify sent or completed campaign")

    update_data = data.copy()
    update_data.pop("id", None)
    update_data.pop("tenant_id", None)
    update_data.pop("created_by_id", None)
    update_data.pop("created_at", None)

    for field, value in update_data.items():
        if field in ['custom_fields', 'description', 'from_email', 'from_name', 'name', 'reply_to', 'subject']:
            setattr(campaign, field, value)

    campaign.updated_by_id = user.id
    await db.commit()
    await db.refresh(campaign)
    return {"id": str(campaign.id), "message": "Campaign updated"}


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: UUID,
    current_user: tuple = Depends(require_campaigns_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete a campaign (only draft campaigns)."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status not in [CampaignStatusEnum.DRAFT, CampaignStatusEnum.CANCELLED]:
        raise HTTPException(status_code=400, detail="Can only delete draft or cancelled campaigns")

    await db.delete(campaign)
    await db.commit()


# =============================================================================
# Campaign Actions
# =============================================================================

@router.post("/{campaign_id}/send", response_model=dict)
async def send_campaign(
    campaign_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: tuple = Depends(require_campaigns_send),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Send or schedule a campaign."""
    user, _ = current_user

    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
        .options(
            selectinload(Campaign.audience),
            selectinload(Campaign.templates),
            selectinload(Campaign.sequences),
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status not in [CampaignStatusEnum.DRAFT, CampaignStatusEnum.SCHEDULED, CampaignStatusEnum.PAUSED]:
        raise HTTPException(status_code=400, detail="Campaign cannot be sent in current state")

    # Validate campaign has audience and templates
    if not campaign.audience or campaign.audience.estimated_count == 0:
        raise HTTPException(status_code=400, detail="Campaign has no audience")

    if campaign.type == CampaignTypeEnum.BROADCAST and not campaign.templates:
        raise HTTPException(status_code=400, detail="Broadcast campaign needs at least one template")

    if campaign.type == CampaignTypeEnum.SEQUENCE and not campaign.sequences:
        raise HTTPException(status_code=400, detail="Sequence campaign needs at least one sequence step")

    # Check daily limit
    sending_domain = None
    if campaign.sending_domain_id:
        result = await db.execute(
            select(SendingDomain).where(SendingDomain.id == campaign.sending_domain_id)
        )
        sending_domain = result.scalar_one_or_none()

    if sending_domain:
        today = datetime.now(timezone.utc).date()
        if sending_domain.last_sent_date and sending_domain.last_sent_date.date() == today:
            if sending_domain.current_daily_count >= sending_domain.daily_limit:
                raise HTTPException(status_code=400, detail="Daily sending limit reached for this domain")

    # Queue campaign for sending
    from app.workers.tasks.campaign_tasks_v2 import send_campaign_task
    send_campaign_task.delay(str(tenant_id), str(campaign_id), str(user.id))

    campaign.status = CampaignStatusEnum.SENDING
    campaign.sent_at = datetime.now(timezone.utc)
    campaign.updated_by_id = user.id
    await db.commit()

    return {"message": "Campaign queued for sending", "campaign_id": str(campaign_id)}


@router.post("/{campaign_id}/schedule", response_model=dict)
async def schedule_campaign(
    campaign_id: UUID,
    scheduled_at: datetime,
    current_user: tuple = Depends(require_campaigns_send),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Schedule a campaign for later sending."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status != CampaignStatusEnum.DRAFT:
        raise HTTPException(status_code=400, detail="Can only schedule draft campaigns")

    if scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Scheduled time must be in the future")

    campaign.status = CampaignStatusEnum.SCHEDULED
    campaign.scheduled_at = scheduled_at
    await db.commit()

    return {"message": "Campaign scheduled", "scheduled_at": scheduled_at.isoformat()}


@router.post("/{campaign_id}/pause", response_model=dict)
async def pause_campaign(
    campaign_id: UUID,
    current_user: tuple = Depends(require_campaigns_send),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Pause a sending campaign."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status != CampaignStatusEnum.SENDING:
        raise HTTPException(status_code=400, detail="Can only pause sending campaigns")

    campaign.status = CampaignStatusEnum.PAUSED
    await db.commit()

    return {"message": "Campaign paused"}


@router.post("/{campaign_id}/resume", response_model=dict)
async def resume_campaign(
    campaign_id: UUID,
    current_user: tuple = Depends(require_campaigns_send),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Resume a paused campaign."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status != CampaignStatusEnum.PAUSED:
        raise HTTPException(status_code=400, detail="Can only resume paused campaigns")

    from app.workers.tasks.campaign_tasks_v2 import send_campaign_task
    send_campaign_task.delay(str(tenant_id), str(campaign_id), str(current_user[0].id))

    campaign.status = CampaignStatusEnum.SENDING
    await db.commit()

    return {"message": "Campaign resumed"}


@router.post("/{campaign_id}/cancel", response_model=dict)
async def cancel_campaign(
    campaign_id: UUID,
    current_user: tuple = Depends(require_campaigns_send),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Cancel a campaign."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status in [CampaignStatusEnum.SENT, CampaignStatusEnum.COMPLETED]:
        raise HTTPException(status_code=400, detail="Cannot cancel sent or completed campaign")

    campaign.status = CampaignStatusEnum.CANCELLED
    campaign.completed_at = datetime.now(timezone.utc)
    await db.commit()

    return {"message": "Campaign cancelled"}


# =============================================================================
# Audience Management
# =============================================================================

@router.get("/{campaign_id}/audience", response_model=dict)
async def get_audience(
    campaign_id: UUID,
    current_user: tuple = Depends(require_campaigns_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get campaign audience."""
    result = await db.execute(
        select(CampaignAudience).where(
            CampaignAudience.campaign_id == campaign_id,
            CampaignAudience.tenant_id == tenant_id,
        )
    )
    audience = result.scalar_one_or_none()
    if not audience:
        raise HTTPException(status_code=404, detail="Audience not found")

    return {
        "id": str(audience.id),
        "type": audience.type.value,
        "name": audience.name,
        "contact_ids": audience.contact_ids,
        "filters": audience.filters,
        "exclude_contact_ids": audience.exclude_contact_ids,
        "exclude_suppressed": audience.exclude_suppressed,
        "exclude_unsubscribed": audience.exclude_unsubscribed,
        "exclude_bounced": audience.exclude_bounced,
        "estimated_count": audience.estimated_count,
        "last_computed_at": audience.last_computed_at,
    }


@router.patch("/{campaign_id}/audience", response_model=dict)
async def update_audience(
    campaign_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_campaigns_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update campaign audience."""
    user, _ = current_user

    result = await db.execute(
        select(CampaignAudience).where(
            CampaignAudience.campaign_id == campaign_id,
            CampaignAudience.tenant_id == tenant_id,
        )
    )
    audience = result.scalar_one_or_none()
    if not audience:
        raise HTTPException(status_code=404, detail="Audience not found")

    # Update fields
    for field in ["type", "name", "contact_ids", "filters", "exclude_contact_ids",
                  "exclude_suppressed", "exclude_unsubscribed", "exclude_bounced"]:
        if field in data:
            setattr(audience, field, data[field])

    # Recompute estimated count if static
    if audience.type == AudienceTypeEnum.STATIC and "contact_ids" in data:
        audience.estimated_count = len(data["contact_ids"])
        audience.last_computed_at = datetime.now(timezone.utc)

    audience.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(audience)

    return {"id": str(audience.id), "message": "Audience updated", "estimated_count": audience.estimated_count}


@router.post("/{campaign_id}/audience/compute", response_model=dict)
async def compute_audience(
    campaign_id: UUID,
    current_user: tuple = Depends(require_campaigns_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Compute dynamic audience count."""
    result = await db.execute(
        select(CampaignAudience).where(
            CampaignAudience.campaign_id == campaign_id,
            CampaignAudience.tenant_id == tenant_id,
        )
    )
    audience = result.scalar_one_or_none()
    if not audience:
        raise HTTPException(status_code=404, detail="Audience not found")

    if audience.type == AudienceTypeEnum.DYNAMIC and audience.filters:
        # Build query based on filters
        query = select(func.count()).select_from(Contact).where(Contact.tenant_id == tenant_id)

        filters = audience.filters
        if "status" in filters:
            query = query.where(Contact.lead_status.in_(filters["status"]))
        if "tags" in filters:
            query = query.where(Contact.tags.overlap(filters["tags"]))
        if "source" in filters:
            query = query.where(Contact.source == filters["source"])

        # Exclude suppressed/unsubscribed/bounced
        if audience.exclude_suppressed:
            # Join with suppression list
            pass

        count = await db.scalar(query)
        audience.estimated_count = count
    else:
        audience.estimated_count = len(audience.contact_ids)

    audience.last_computed_at = datetime.now(timezone.utc)
    await db.commit()

    return {"estimated_count": audience.estimated_count}


# =============================================================================
# Templates
# =============================================================================

@router.post("/{campaign_id}/templates", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_template(
    campaign_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_campaigns_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a campaign template."""
    # Verify campaign exists
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Get next step_order
    result = await db.execute(
        select(func.max(CampaignTemplate.step_order)).where(CampaignTemplate.campaign_id == campaign_id)
    )
    max_order = result.scalar() or 0

    template = CampaignTemplate(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        step_order=data.get("step_order", max_order + 1),
        **{k: v for k, v in data.items() if k != "step_order"},
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return {"id": str(template.id), "message": "Template created"}


@router.get("/{campaign_id}/templates", response_model=List[dict])
async def list_templates(
    campaign_id: UUID,
    current_user: tuple = Depends(require_campaigns_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List campaign templates."""
    result = await db.execute(
        select(CampaignTemplate)
        .where(CampaignTemplate.campaign_id == campaign_id, CampaignTemplate.tenant_id == tenant_id)
        .order_by(CampaignTemplate.step_order)
    )
    templates = result.scalars().all()

    return [{
        "id": str(t.id),
        "step_order": t.step_order,
        "name": t.name,
        "subject": t.subject,
        "preheader": t.preheader,
        "html_content": t.html_content,
        "text_content": t.text_content,
        "ai_personalization_enabled": t.ai_personalization_enabled,
        "version": t.version,
        "is_active_version": t.is_active_version,
    } for t in templates]


@router.patch("/templates/{template_id}", response_model=dict)
async def update_template(
    template_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_campaigns_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a template (creates new version per blueprint)."""
    result = await db.execute(
        select(CampaignTemplate).where(CampaignTemplate.id == template_id, CampaignTemplate.tenant_id == tenant_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Versioning: create new version if content changed
    content_fields = ["subject", "preheader", "html_content", "text_content"]
    content_changed = any(
        field in data and data[field] != getattr(template, field)
        for field in content_fields
    )

    if content_changed:
        # Deactivate current version
        template.is_active_version = False
        # Create new version
        new_template = CampaignTemplate(
            tenant_id=tenant_id,
            campaign_id=template.campaign_id,
            step_order=template.step_order,
            name=template.name,
            subject=data.get("subject", template.subject),
            preheader=data.get("preheader", template.preheader),
            html_content=data.get("html_content", template.html_content),
            text_content=data.get("text_content", template.text_content),
            ai_personalization_enabled=data.get("ai_personalization_enabled", template.ai_personalization_enabled),
            ai_personalization_prompt=data.get("ai_personalization_prompt", template.ai_personalization_prompt),
            version=template.version + 1,
            is_active_version=True,
        )
        db.add(new_template)
        await db.commit()
        await db.refresh(new_template)
        return {"id": str(new_template.id), "message": "New template version created", "version": new_template.version}

    # Just update metadata
    for field in ["name", "ai_personalization_enabled", "ai_personalization_prompt"]:
        if field in data:
            setattr(template, field, data[field])

    await db.commit()
    return {"id": str(template.id), "message": "Template updated"}


# =============================================================================
# Sequences
# =============================================================================

@router.post("/{campaign_id}/sequences", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_sequence_step(
    campaign_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_campaigns_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a sequence step."""
    # Verify campaign is sequence type
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.type != CampaignTypeEnum.SEQUENCE:
        raise HTTPException(status_code=400, detail="Campaign is not a sequence type")

    # Verify template exists
    template_id = data.get("template_id")
    result = await db.execute(
        select(CampaignTemplate).where(
            CampaignTemplate.id == template_id,
            CampaignTemplate.campaign_id == campaign_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Template not found in this campaign")

    # Get next step_order
    result = await db.execute(
        select(func.max(CampaignSequence.step_order)).where(CampaignSequence.campaign_id == campaign_id)
    )
    max_order = result.scalar() or 0

    sequence = CampaignSequence(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        step_order=data.get("step_order", max_order + 1),
        **{k: v for k, v in data.items() if k != "step_order"},
    )
    db.add(sequence)
    await db.commit()
    await db.refresh(sequence)

    return {"id": str(sequence.id), "message": "Sequence step created"}


@router.get("/{campaign_id}/sequences", response_model=List[dict])
async def list_sequences(
    campaign_id: UUID,
    current_user: tuple = Depends(require_campaigns_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List campaign sequence steps."""
    result = await db.execute(
        select(CampaignSequence)
        .where(CampaignSequence.campaign_id == campaign_id, CampaignSequence.tenant_id == tenant_id)
        .options(selectinload(CampaignSequence.template))
        .order_by(CampaignSequence.step_order)
    )
    sequences = result.scalars().all()

    return [{
        "id": str(s.id),
        "step_order": s.step_order,
        "template_id": str(s.template_id),
        "template_name": s.template.name if s.template else None,
        "delay_days": s.delay_days,
        "delay_hours": s.delay_hours,
        "send_time": s.send_time,
        "send_timezone": s.send_timezone,
        "send_on_weekends": s.send_on_weekends,
        "stop_on_reply": s.stop_on_reply,
        "stop_on_unsubscribe": s.stop_on_unsubscribe,
        "stop_on_bounce": s.stop_on_bounce,
    } for s in sequences]


@router.patch("/sequences/{sequence_id}", response_model=dict)
async def update_sequence(
    sequence_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_campaigns_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a sequence step."""
    result = await db.execute(
        select(CampaignSequence).where(CampaignSequence.id == sequence_id, CampaignSequence.tenant_id == tenant_id)
    )
    sequence = result.scalar_one_or_none()
    if not sequence:
        raise HTTPException(status_code=404, detail="Sequence step not found")

    for field in ["template_id", "delay_days", "delay_hours", "send_time", "send_timezone",
                  "send_on_weekends", "stop_on_reply", "stop_on_unsubscribe", "stop_on_bounce"]:
        if field in data:
            setattr(sequence, field, data[field])

    await db.commit()
    return {"id": str(sequence.id), "message": "Sequence updated"}


@router.delete("/sequences/{sequence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sequence(
    sequence_id: UUID,
    current_user: tuple = Depends(require_campaigns_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete a sequence step."""
    result = await db.execute(
        select(CampaignSequence).where(CampaignSequence.id == sequence_id, CampaignSequence.tenant_id == tenant_id)
    )
    sequence = result.scalar_one_or_none()
    if not sequence:
        raise HTTPException(status_code=404, detail="Sequence step not found")

    await db.delete(sequence)
    await db.commit()


# =============================================================================
# Triggers
# =============================================================================

@router.post("/{campaign_id}/triggers", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_trigger(
    campaign_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_campaigns_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a triggered campaign rule."""
    # Verify campaign is triggered type
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.type != CampaignTypeEnum.TRIGGERED:
        raise HTTPException(status_code=400, detail="Campaign is not a triggered type")

    # Verify template
    template_id = data.get("template_id")
    result = await db.execute(
        select(CampaignTemplate).where(
            CampaignTemplate.id == template_id,
            CampaignTemplate.campaign_id == campaign_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Template not found in this campaign")

    trigger = CampaignTrigger(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        **data,
    )
    db.add(trigger)
    await db.commit()
    await db.refresh(trigger)

    return {"id": str(trigger.id), "message": "Trigger created"}


@router.get("/{campaign_id}/triggers", response_model=List[dict])
async def list_triggers(
    campaign_id: UUID,
    current_user: tuple = Depends(require_campaigns_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List campaign triggers."""
    result = await db.execute(
        select(CampaignTrigger)
        .where(CampaignTrigger.campaign_id == campaign_id, CampaignTrigger.tenant_id == tenant_id)
        .options(selectinload(CampaignTrigger.template))
    )
    triggers = result.scalars().all()

    return [{
        "id": str(t.id),
        "trigger_type": t.trigger_type.value,
        "name": t.name,
        "conditions": t.conditions,
        "template_id": str(t.template_id),
        "template_name": t.template.name if t.template else None,
        "delay_minutes": t.delay_minutes,
        "max_triggers_per_contact": t.max_triggers_per_contact,
        "cooldown_hours": t.cooldown_hours,
        "is_active": t.is_active,
    } for t in triggers]


@router.patch("/triggers/{trigger_id}", response_model=dict)
async def update_trigger(
    trigger_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_campaigns_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a trigger."""
    result = await db.execute(
        select(CampaignTrigger).where(CampaignTrigger.id == trigger_id, CampaignTrigger.tenant_id == tenant_id)
    )
    trigger = result.scalar_one_or_none()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    for field in ["name", "conditions", "template_id", "delay_minutes",
                  "max_triggers_per_contact", "cooldown_hours", "is_active"]:
        if field in data:
            setattr(trigger, field, data[field])

    await db.commit()
    return {"id": str(trigger.id), "message": "Trigger updated"}


@router.delete("/triggers/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trigger(
    trigger_id: UUID,
    current_user: tuple = Depends(require_campaigns_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete a trigger."""
    result = await db.execute(
        select(CampaignTrigger).where(CampaignTrigger.id == trigger_id, CampaignTrigger.tenant_id == tenant_id)
    )
    trigger = result.scalar_one_or_none()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    await db.delete(trigger)
    await db.commit()


# =============================================================================
# Recipients & Analytics
# =============================================================================

@router.get("/{campaign_id}/recipients", response_model=PaginatedResponse)
async def list_recipients(
    campaign_id: UUID,
    params: PaginationParams = Depends(),
    status: Optional[str] = Query(None),
    current_user: tuple = Depends(require_campaigns_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List campaign recipients with status."""
    query = select(CampaignRecipient).where(
        CampaignRecipient.campaign_id == campaign_id,
        CampaignRecipient.tenant_id == tenant_id,
    ).options(selectinload(CampaignRecipient.contact))

    if status:
        query = query.where(CampaignRecipient.status == status)

    query = query.order_by(CampaignRecipient.created_at.desc())

    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    recipients = result.scalars().all()

    return PaginatedResponse.create(
        items=[{
            "id": str(r.id),
            "contact_id": str(r.contact_id),
            "contact_name": r.contact.full_name if r.contact else None,
            "email": r.email,
            "status": r.status.value,
            "sent_at": r.sent_at,
            "delivered_at": r.delivered_at,
            "opened_at": r.first_opened_at,
            "clicked_at": r.first_clicked_at,
            "replied_at": r.replied_at,
            "bounced_at": r.bounced_at,
            "open_count": r.open_count,
            "click_count": r.click_count,
            "ai_personalized": r.ai_personalized,
        } for r in recipients],
        total=total,
        params=params,
    )


@router.get("/{campaign_id}/analytics", response_model=dict)
async def get_campaign_analytics(
    campaign_id: UUID,
    current_user: tuple = Depends(require_campaigns_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get detailed campaign analytics."""
    result = await db.execute(
        select(CampaignStats).where(
            CampaignStats.campaign_id == campaign_id,
            CampaignStats.tenant_id == tenant_id,
        )
    )
    stats = result.scalar_one_or_none()
    if not stats:
        # Return computed stats if not cached
        return {"message": "Stats not yet computed"}

    return {
        "delivery": {
            "total": stats.total_recipients,
            "queued": stats.queued,
            "sent": stats.sent,
            "delivered": stats.delivered,
            "failed": stats.failed,
            "bounced": stats.bounced,
            "suppressed": stats.suppressed,
            "delivery_rate": stats.delivery_rate,
        },
        "engagement": {
            "opened": stats.opened,
            "clicked": stats.clicked,
            "replied": stats.replied,
            "unsubscribed": stats.unsubscribed,
            "complained": stats.complained,
            "open_rate": stats.open_rate,
            "click_rate": stats.click_rate,
            "reply_rate": stats.reply_rate,
        },
        "sales": {
            "interested": stats.interested,
            "qualified_leads": stats.qualified_leads,
            "appointments": stats.appointments,
            "proposals": stats.proposals,
            "conversions": stats.conversions,
            "revenue": stats.revenue,
            "conversion_rate": stats.conversion_rate,
        },
        "ai": {
            "personalized_count": stats.ai_personalized_count,
            "cost_usd": stats.ai_cost_usd,
            "reply_classifications": stats.ai_reply_classifications,
        },
        "last_calculated": stats.last_calculated_at,
    }