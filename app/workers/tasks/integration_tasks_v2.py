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
    """Sync leads from an integration."""
    logger.info("Syncing integration", integration_id=integration_id, sync_log_id=sync_log_id)
    
    async def _sync():
        async with tenant_db_context(tenant_id) as db:
            # Load integration with credentials
            result = await db.execute(
                select(Integration)
                .where(Integration.id == UUID(integration_id))
                .options(selectinload(Integration.credentials))
            )
            integration = result.scalar_one_or_none()
            if not integration:
                logger.error("Integration not found", integration_id=integration_id)
                return

            # Load sync log
            sync_log_result = await db.execute(
                select(IntegrationSyncLog).where(IntegrationSyncLog.id == UUID(sync_log_id))
            )
            sync_log = sync_log_result.scalar_one_or_none()
            if not sync_log:
                logger.error("Sync log not found", sync_log_id=sync_log_id)
                return

            # Update sync log status
            sync_log.status = SyncStatusEnum.RUNNING
            sync_log.started_at = datetime.now(timezone.utc)
            await db.commit()

            try:
                # Get active credentials
                active_creds = [c for c in integration.credentials if c.is_active]
                if not active_creds:
                    raise ValueError("No active credentials")

                cred = active_creds[0]
                import json
                credentials = json.loads(cred.credentials_encrypted)
                credentials.update({
                    "access_token": cred.access_token,
                    "refresh_token": cred.refresh_token,
                    "token_expires_at": cred.token_expires_at.isoformat() if cred.token_expires_at else None,
                    "token_type": cred.token_type,
                })

                # Sync
                integration_service = IntegrationService()
                
                since = None
                if not full_sync and integration.last_sync_at:
                    since = integration.last_sync_at

                result = await integration_service.sync_integration(
                    integration_type=integration.type.value,
                    integration_config=integration.config,
                    credentials=credentials,
                    since=since,
                    limit=1000,
                )

                # Process leads
                leads_created = 0
                leads_updated = 0
                leads_failed = 0

                if result.leads:
                    for lead_data in result.leads:
                        try:
                            await _process_lead(db, integration, lead_data)
                            leads_created += 1
                        except Exception as e:
                            logger.error("Failed to process lead", error=type(e).__name__)
                            leads_failed += 1

                # Update integration
                integration.last_sync_at = datetime.now(timezone.utc)
                integration.last_sync_status = SyncStatusEnum.COMPLETED if result.success else SyncStatusEnum.FAILED
                integration.last_sync_error = result.error_message
                integration.records_synced += result.records_created

                # Update sync log
                sync_log.status = SyncStatusEnum.COMPLETED if result.success else SyncStatusEnum.FAILED
                sync_log.completed_at = datetime.now(timezone.utc)
                sync_log.duration_seconds = (sync_log.completed_at - sync_log.started_at).total_seconds()
                sync_log.records_processed = result.records_processed
                sync_log.records_created = leads_created
                sync_log.records_updated = leads_updated
                sync_log.records_failed = leads_failed
                sync_log.records_skipped = result.records_skipped
                sync_log.error_message = result.error_message
                sync_log.error_details = result.error_details

                await db.commit()
                logger.info("Sync completed", 
                           integration_id=integration_id, 
                           success=result.success,
                           created=leads_created,
                           failed=leads_failed)

            except Exception as e:
                logger.error("Sync failed", integration_id=integration_id, error=type(e).__name__)
                
                sync_log.status = SyncStatusEnum.FAILED
                sync_log.completed_at = datetime.now(timezone.utc)
                sync_log.duration_seconds = (datetime.now(timezone.utc) - sync_log.started_at).total_seconds()
                sync_log.error_message = type(e).__name__
                
                integration.last_sync_status = SyncStatusEnum.FAILED
                integration.last_sync_error = type(e).__name__
                integration.last_sync_at = datetime.now(timezone.utc)
                
                await db.commit()

    asyncio.run(_sync())


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
    """Run scheduled sync for all integrations with sync_enabled=True."""
    logger.info("Running scheduled integration syncs")
    
    async def _sync_all():
        async with tenant_db_context(tenant_id) as db:
            now = datetime.now(timezone.utc)
            
            result = await db.execute(
                select(Integration).where(
                    Integration.sync_enabled == True,
                    Integration.status == IntegrationStatusEnum.CONNECTED,
                ).options(selectinload(Integration.credentials))
            )
            integrations = result.scalars().all()

            for integration in integrations:
                # Check if sync is due
                if integration.last_sync_at:
                    next_sync = integration.last_sync_at + timedelta(minutes=integration.sync_frequency_minutes)
                    if next_sync > now:
                        continue
                
                # Check credentials
                active_creds = [c for c in integration.credentials if c.is_active]
                if not active_creds:
                    continue

                # Create sync log
                sync_log = IntegrationSyncLog(
                    tenant_id=integration.tenant_id,
                    integration_id=integration.id,
                    sync_type="incremental",
                    triggered_by="scheduled",
                )
                db.add(sync_log)
                await db.flush()

                # Queue sync task
                sync_integration_task.delay(tenant_id, str(integration.id), str(sync_log.id), False)

            await db.commit()

    asyncio.run(_sync_all())


@shared_task
def validate_all_integrations(tenant_id: str):
    """Validate all integration credentials."""
    logger.info("Validating all integrations")
    
    async def _validate():
        async with tenant_db_context(tenant_id) as db:
            result = await db.execute(
                select(Integration)
                .where(Integration.status.in_([IntegrationStatusEnum.CONNECTED, IntegrationStatusEnum.PENDING]))
                .options(selectinload(Integration.credentials))
            )
            integrations = result.scalars().all()

            integration_service = IntegrationService()

            for integration in integrations:
                active_creds = [c for c in integration.credentials if c.is_active]
                if not active_creds:
                    continue

                cred = active_creds[0]
                import json
                credentials = json.loads(cred.credentials_encrypted)
                credentials.update({
                    "access_token": cred.access_token,
                    "refresh_token": cred.refresh_token,
                })

                is_valid = await integration_service.validate_integration(
                    integration.type.value, credentials
                )

                cred.last_validated_at = datetime.now(timezone.utc)
                cred.validation_error = None if is_valid else "Validation failed"
                
                integration.status = IntegrationStatusEnum.CONNECTED if is_valid else IntegrationStatusEnum.ERROR

            await db.commit()

    asyncio.run(_validate())