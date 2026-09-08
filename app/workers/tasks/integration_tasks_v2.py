"""
Integration Celery tasks for Globexa CRM.
"""
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone, timedelta
from uuid import UUID
import structlog
import asyncio

from app.core.tenant_context import tenant_db_context
from app.models import (
    Integration, IntegrationCredential, WebhookEndpoint, IntegrationSyncLog,
    LeadSourceConfig, Touchpoint, Contact, Company, Lead,
    IntegrationTypeEnum, IntegrationStatusEnum, SyncStatusEnum,
    LeadSourceEnum
)
from app.services.integration.adapter import IntegrationService, LeadData

logger = structlog.get_logger()


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def sync_integration_task(self, tenant_id: str, integration_id: str, sync_log_id: str, full_sync: bool = False):
    raise ValueError("Use execute_operation with a persisted integration sync job ID")


async def _process_lead(db: AsyncSession, integration: Integration, lead_data: LeadData):
    """Process a lead from integration - create/update contact, company, lead."""
    tenant_id = integration.tenant_id
    
    # Find or create company
    company = None
    if lead_data.company_name or lead_data.company_domain:
        query = select(Company).where(Company.tenant_id == tenant_id)
        if lead_data.company_domain:
            query = query.where(Company.domain == lead_data.company_domain)
        elif lead_data.company_name:
            query = query.where(Company.name == lead_data.company_name)
        
        result = await db.execute(query)
        company = result.scalar_one_or_none()
        
        if not company and (lead_data.company_name or lead_data.company_domain):
            company = Company(
                tenant_id=tenant_id,
                name=lead_data.company_name or lead_data.company_domain,
                domain=lead_data.company_domain,
                source=LeadSourceEnum(integration.type.value) if integration.type.value in [e.value for e in LeadSourceEnum] else LeadSourceEnum.OTHER,
                custom_fields=lead_data.custom_fields or {},
            )
            db.add(company)
            await db.flush()

    # Find or create contact
    contact = None
    if lead_data.email:
        result = await db.execute(
            select(Contact).where(
                Contact.tenant_id == tenant_id,
                Contact.email == lead_data.email,
            )
        )
        contact = result.scalar_one_or_none()
    
    if not contact:
        contact = Contact(
            tenant_id=tenant_id,
            email=lead_data.email,
            first_name=lead_data.first_name,
            last_name=lead_data.last_name,
            phone=lead_data.phone,
            mobile=lead_data.mobile,
            title=lead_data.title,
            company_id=company.id if company else None,
            source=LeadSourceEnum(integration.type.value) if integration.type.value in [e.value for e in LeadSourceEnum] else LeadSourceEnum.OTHER,
            utm_source=lead_data.utm_source,
            utm_medium=lead_data.utm_medium,
            utm_campaign=lead_data.utm_campaign,
            utm_content=lead_data.utm_content,
            utm_term=lead_data.utm_term,
            referrer_url=lead_data.referrer_url,
            landing_page=lead_data.landing_page,
            custom_fields=lead_data.custom_fields or {},
        )
        db.add(contact)
        await db.flush()
    else:
        # Update existing contact with new info
        if lead_data.first_name and not contact.first_name:
            contact.first_name = lead_data.first_name
        if lead_data.last_name and not contact.last_name:
            contact.last_name = lead_data.last_name
        if lead_data.phone and not contact.phone:
            contact.phone = lead_data.phone
        if lead_data.title and not contact.title:
            contact.title = lead_data.title
        if company and not contact.company_id:
            contact.company_id = company.id

    # Create lead
    # Check if lead already exists for this source
    existing_lead = None
    if lead_data.source_id:
        result = await db.execute(
            select(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.source == LeadSourceEnum(integration.type.value) if integration.type.value in [e.value for e in LeadSourceEnum] else LeadSourceEnum.OTHER,
                Lead.source_id == lead_data.source_id,
            )
        )
        existing_lead = result.scalar_one_or_none()

    if existing_lead:
        # Update existing lead
        existing_lead.description = (existing_lead.description or "") + f"\n[Sync {datetime.now(timezone.utc)}] {lead_data.custom_fields}"
        existing_lead.updated_at = datetime.now(timezone.utc)
    else:
        lead = Lead(
            tenant_id=tenant_id,
            contact_id=contact.id,
            company_id=company.id if company else None,
            title=lead_data.custom_fields.get("title", "New Lead") if lead_data.custom_fields else "New Lead",
            description=f"Synced from {integration.name}",
            status="new",
            source=LeadSourceEnum(integration.type.value) if integration.type.value in [e.value for e in LeadSourceEnum] else LeadSourceEnum.OTHER,
            source_id=lead_data.source_id,
            utm_source=lead_data.utm_source,
            utm_medium=lead_data.utm_medium,
            utm_campaign=lead_data.utm_campaign,
            utm_content=lead_data.utm_content,
            utm_term=lead_data.utm_term,
            referrer_url=lead_data.referrer_url,
            landing_page=lead_data.landing_page,
            custom_fields=lead_data.custom_fields or {},
        )
        db.add(lead)

    # Create touchpoint for attribution
    touchpoint = Touchpoint(
        tenant_id=tenant_id,
        contact_id=contact.id,
        lead_id=existing_lead.id if existing_lead else None,
        source=lead_data.source or integration.type.value,
        medium=lead_data.medium or "integration",
        campaign=lead_data.campaign,
        utm_source=lead_data.utm_source,
        utm_medium=lead_data.utm_medium,
        utm_campaign=lead_data.utm_campaign,
        utm_content=lead_data.utm_content,
        utm_term=lead_data.utm_term,
        referrer_url=lead_data.referrer_url,
        landing_page=lead_data.landing_page,
        interaction_type="integration_sync",
        integration_id=integration.id,
        external_id=lead_data.source_id,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(touchpoint)

    # Create activity
    from app.models import Activity, ActivityTypeEnum
    activity = Activity(
        tenant_id=tenant_id,
        lead_id=existing_lead.id if existing_lead else None,
        contact_id=contact.id,
        company_id=company.id if company else None,
        type=ActivityTypeEnum.LEAD_CREATED if not existing_lead else ActivityTypeEnum.NOTE,
        subject=f"Lead synced from {integration.name}",
        description=f"Lead synced from {integration.type.value} integration",
        is_ai_generated=False,
    )
    db.add(activity)


@shared_task
def process_webhook_task(tenant_id: str, event_id: str):
    """Only previously verified, persisted ingress events may enter processing."""
    from app.workers.tasks.foundation_tasks import deliver_event
    return deliver_event.run(tenant_id=tenant_id, event_id=event_id)


async def _create_lead_from_webhook(db: AsyncSession, tenant_id: UUID, lead_data: LeadData, webhook: WebhookEndpoint):
    """Create lead from generic webhook."""
    # Similar to _process_lead but without integration context
    contact = None
    if lead_data.email:
        result = await db.execute(
            select(Contact).where(Contact.tenant_id == tenant_id, Contact.email == lead_data.email)
        )
        contact = result.scalar_one_or_none()

    if not contact:
        contact = Contact(
            tenant_id=tenant_id,
            email=lead_data.email,
            first_name=lead_data.first_name,
            last_name=lead_data.last_name,
            phone=lead_data.phone,
            title=lead_data.title,
            source=LeadSourceEnum.WEBHOOK,
            custom_fields=lead_data.custom_fields or {},
        )
        db.add(contact)
        await db.flush()

    # Create lead
    lead = Lead(
        tenant_id=tenant_id,
        contact_id=contact.id,
        title=lead_data.custom_fields.get("title", "Webhook Lead") if lead_data.custom_fields else "Webhook Lead",
        description=f"Received via webhook: {webhook.name}",
        status="new",
        source=LeadSourceEnum.WEBHOOK,
        source_id=lead_data.source_id,
        custom_fields=lead_data.custom_fields or {},
    )
    db.add(lead)
    await db.flush()

    # Touchpoint
    touchpoint = Touchpoint(
        tenant_id=tenant_id,
        contact_id=contact.id,
        lead_id=lead.id,
        source=lead_data.source or "webhook",
        medium=lead_data.medium or "webhook",
        utm_source=lead_data.utm_source,
        utm_medium=lead_data.utm_medium,
        utm_campaign=lead_data.utm_campaign,
        interaction_type="webhook",
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(touchpoint)


@shared_task
def scheduled_integration_sync(tenant_id: str):
    from app.workers.tasks.crm_tasks import crm_tick
    return crm_tick.run(tenant_id)


@shared_task
def validate_all_integrations(tenant_id: str):
    raise ValueError("Use the permission-checked integration validation API")
