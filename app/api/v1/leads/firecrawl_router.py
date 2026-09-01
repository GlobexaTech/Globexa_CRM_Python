"""
Firecrawl Lead Search and Approval API routes for Globexa CRM.
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import get_current_active_user, require_leads_write, require_leads_read, get_tenant_id
from app.schemas import (
    FirecrawlSearchRequest,
    FirecrawlSearchResponse,
    FirecrawlSearchResult,
    LeadSourceApprovalRequest,
    LeadSourceApprovalResponse,
    PendingLeadReview,
    BulkLeadApprovalRequest,
    BulkLeadApprovalResponse,
    LeadCreate,
    LeadResponse,
    PaginationParams,
    PaginatedResponse,
)
from app.models import (
    Lead, Contact, Company, User, Integration, IntegrationStatusEnum,
    PendingLead, PendingLeadStatusEnum, Activity, ActivityTypeEnum
)
from app.services.integration import IntegrationService, FirecrawlAdapter
from app.services.integration.adapter import LeadData

router = APIRouter(prefix="/leads/firecrawl", tags=["Leads - Firecrawl"])


@router.post("/search", response_model=FirecrawlSearchResponse)
async def search_leads_firecrawl(
    request: FirecrawlSearchRequest,
    current_user: tuple = Depends(require_leads_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Search for leads using Firecrawl web search.
    Returns raw leads that are stored as pending leads for approval.
    """
    user, _ = current_user
    
    # Find Firecrawl integration for this tenant
    result = await db.execute(
        select(Integration).where(
            Integration.tenant_id == tenant_id,
            Integration.type == "firecrawl",
            Integration.status == IntegrationStatusEnum.CONNECTED,
        )
    )
    integration = result.scalar_one_or_none()
    
    if not integration:
        raise HTTPException(
            status_code=404,
            detail="Firecrawl integration not found or not connected. Please configure it first."
        )
    
    # Get credentials
    credentials = integration.config.get("credentials", {})
    if not credentials.get("api_key"):
        raise HTTPException(
            status_code=400,
            detail="Firecrawl API key not configured in integration settings"
        )
    
    # Search using Firecrawl adapter
    adapter = FirecrawlAdapter()
    
    from app.services.integration.firecrawl_adapter import FirecrawlSearchParams
    search_params = FirecrawlSearchParams(
        query=request.query,
        limit=request.limit,
        location=request.location,
        industry=request.industry,
        company_size=request.company_size,
        technologies=request.technologies,
    )
    
    result = await adapter.search_leads(credentials, search_params)
    
    if not result.success:
        return FirecrawlSearchResponse(
            success=False,
            query=request.query,
            results_count=0,
            leads=[],
            error_message=result.error_message,
        )
    
    # Store as pending leads for approval workflow
    pending_leads = []
    for lead in (result.leads or []):
        # Check if already exists as pending
        existing_result = await db.execute(
            select(PendingLead).where(
                PendingLead.tenant_id == tenant_id,
                PendingLead.source == "firecrawl",
                PendingLead.source_id == lead.raw_data.get("url", ""),
            )
        )
        if existing_result.scalar_one_or_none():
            continue
            
        pending = PendingLead(
            tenant_id=tenant_id,
            source="firecrawl",
            source_id=lead.raw_data.get("url", ""),
            email=lead.email,
            first_name=lead.first_name,
            last_name=lead.last_name,
            title=lead.title,
            company_name=lead.company_name,
            phone=lead.phone,
            raw_data=lead.raw_data,
            status=PendingLeadStatusEnum.PENDING,
            assigned_reviewer_id=user.id,
        )
        db.add(pending)
        pending_leads.append(pending)
    
    await db.commit()
    
    # Convert to response format
    search_results = [
        FirecrawlSearchResult(
            email=lead.email,
            first_name=lead.first_name,
            last_name=lead.last_name,
            title=lead.title,
            company_name=lead.company_name,
            company_domain=lead.company_domain,
            phone=lead.phone,
            source=lead.source,
            medium=lead.medium,
            utm_source=lead.utm_source,
            utm_medium=lead.utm_medium,
            utm_campaign=lead.utm_campaign,
            utm_content=lead.utm_content,
            utm_term=lead.utm_term,
            raw_data=lead.raw_data,
            custom_fields=lead.custom_fields,
        )
        for lead in (result.leads or [])
    ]
    
    return FirecrawlSearchResponse(
        success=True,
        query=request.query,
        results_count=len(search_results),
        leads=search_results,
    )


@router.get("/pending-reviews", response_model=List[PendingLeadReview])
async def get_pending_lead_reviews(
    params: PaginationParams = Depends(),
    source: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: tuple = Depends(require_leads_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Get leads pending review from external sources (Firecrawl, etc.).
    """
    user, membership = current_user
    
    query = select(PendingLead).where(PendingLead.tenant_id == tenant_id)
    
    if source:
        query = query.where(PendingLead.source == source)
    if status:
        query = query.where(PendingLead.status == status)
    
    # Sales executives only see their assigned or unassigned
    if membership.role.value == "sales_executive":
        query = query.where(
            (PendingLead.assigned_reviewer_id == user.id) | 
            (PendingLead.assigned_reviewer_id.is_(None))
        )
    
    query = query.order_by(PendingLead.created_at.desc())
    
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)
    
    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    pending = result.scalars().all()
    
    return [
        PendingLeadReview(
            id=p.id,
            source=p.source,
            source_id=p.source_id,
            email=p.email,
            first_name=p.first_name,
            last_name=p.last_name,
            title=p.title,
            company_name=p.company_name,
            raw_data=p.raw_data,
            created_at=p.created_at,
            assigned_reviewer_id=p.assigned_reviewer_id,
        )
        for p in pending
    ]


@router.post("/approve", response_model=LeadSourceApprovalResponse)
async def approve_reject_lead(
    request: LeadSourceApprovalRequest,
    current_user: tuple = Depends(require_leads_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Approve or reject a lead from external source (Firecrawl, etc.).
    If approved, creates Contact/Lead in CRM and updates PendingLead.
    """
    user, membership = current_user
    
    if request.action not in ["approve", "reject", "needs_review"]:
        raise HTTPException(status_code=400, detail="Invalid action. Must be: approve, reject, or needs_review")
    
    # Find the pending lead
    pending_result = await db.execute(
        select(PendingLead).where(
            PendingLead.tenant_id == tenant_id,
            PendingLead.source == request.source,
            PendingLead.source_id == request.source_id,
        )
    )
    pending = pending_result.scalar_one_or_none()
    
    if not pending:
        raise HTTPException(status_code=404, detail="Pending lead not found")
    
    if request.action == "reject":
        pending.status = PendingLeadStatusEnum.REJECTED
        pending.reviewed_by_id = user.id
        pending.reviewed_at = datetime.now(timezone.utc)
        pending.review_notes = request.reviewer_notes
        await db.commit()
        return LeadSourceApprovalResponse(
            success=True,
            status="rejected",
            message="Lead rejected",
            requires_contact_creation=False,
        )
    
    if request.action == "needs_review":
        pending.status = PendingLeadStatusEnum.NEEDS_REVIEW
        pending.reviewed_by_id = user.id
        pending.reviewed_at = datetime.now(timezone.utc)
        pending.review_notes = request.reviewer_notes
        await db.commit()
        return LeadSourceApprovalResponse(
            success=True,
            status="needs_review",
            message="Lead flagged for additional review",
            requires_contact_creation=False,
        )
    
    # APPROVE - Create contact and lead in CRM
    lead_data = request.lead_data or pending.raw_data
    email = lead_data.get("email", "").lower()
    
    if not email:
        raise HTTPException(status_code=400, detail="Email is required for lead creation")
    
    # Check if contact already exists
    existing_contact_result = await db.execute(
        select(Contact).where(Contact.tenant_id == tenant_id, Contact.email == email)
    )
    existing_contact = existing_contact_result.scalar_one_or_none()
    
    contact = existing_contact
    if not contact:
        # Create new contact
        contact = Contact(
            tenant_id=tenant_id,
            first_name=lead_data.get("first_name", "") or pending.first_name or "",
            last_name=lead_data.get("last_name", "") or pending.last_name or "",
            email=email,
            phone=lead_data.get("phone") or pending.phone,
            title=lead_data.get("title") or pending.title,
            company_name=lead_data.get("company_name") or pending.company_name,
            source=lead_data.get("source", request.source),
            utm_source=lead_data.get("utm_source", "firecrawl"),
            utm_medium=lead_data.get("utm_medium", "organic"),
            utm_campaign=lead_data.get("utm_campaign", request.source),
            custom_fields=lead_data.get("custom_fields", {}),
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(contact)
        await db.flush()
    
    # Check if lead already exists for this contact
    existing_lead_result = await db.execute(
        select(Lead).where(Lead.tenant_id == tenant_id, Lead.contact_id == contact.id)
    )
    existing_lead = existing_lead_result.scalar_one_or_none()
    
    if existing_lead:
        # Update pending lead reference
        pending.status = PendingLeadStatusEnum.APPROVED
        pending.reviewed_by_id = user.id
        pending.reviewed_at = datetime.now(timezone.utc)
        pending.created_lead_id = existing_lead.id
        pending.created_contact_id = contact.id
        await db.commit()
        return LeadSourceApprovalResponse(
            success=True,
            lead_id=existing_lead.id,
            status="approved",
            message="Lead already exists for this contact",
            requires_contact_creation=False,
        )
    
    # Create lead
    lead = Lead(
        tenant_id=tenant_id,
        contact_id=contact.id,
        company_id=lead_data.get("company_id"),
        title=lead_data.get("title", f"Inbound from {request.source}"),
        description=lead_data.get("description"),
        status="new",
        owner_id=user.id,  # Assign to approver by default
        source=lead_data.get("source", request.source),
        source_id=lead_data.get("source_id") or pending.source_id,
        utm_source=lead_data.get("utm_source", "firecrawl"),
        utm_medium=lead_data.get("utm_medium", "organic"),
        utm_campaign=lead_data.get("utm_campaign", request.source),
        utm_content=lead_data.get("utm_content"),
        utm_term=lead_data.get("utm_term"),
        referrer_url=lead_data.get("referrer_url"),
        landing_page=lead_data.get("landing_page"),
        custom_fields=lead_data.get("custom_fields", {}),
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(lead)
    await db.flush()
    
    # Update pending lead
    pending.status = PendingLeadStatusEnum.APPROVED
    pending.reviewed_by_id = user.id
    pending.reviewed_at = datetime.now(timezone.utc)
    pending.review_notes = request.reviewer_notes
    pending.created_lead_id = lead.id
    pending.created_contact_id = contact.id
    
    # Create activity
    activity = Activity(
        tenant_id=tenant_id,
        lead_id=lead.id,
        contact_id=contact.id,
        type=ActivityTypeEnum.AI_ACTION,
        subject=f"Lead approved from {request.source}",
        description=f"Lead imported from {request.source} and approved by {user.full_name}",
        user_id=user.id,
        is_ai_generated=False,
        metadata={"source": request.source, "source_id": request.source_id},
    )
    db.add(activity)
    await db.commit()
    await db.refresh(lead)
    
    return LeadSourceApprovalResponse(
        success=True,
        lead_id=lead.id,
        status="approved",
        message="Lead approved and created in CRM",
        requires_contact_creation=not existing_contact,
    )


@router.post("/bulk-approve", response_model=BulkLeadApprovalResponse)
async def bulk_approve_leads(
    request: BulkLeadApprovalRequest,
    current_user: tuple = Depends(require_leads_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Bulk approve or reject multiple pending leads.
    """
    user, membership = current_user
    
    if request.action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Invalid action. Must be: approve or reject")
    
    approved = 0
    rejected = 0
    failed = 0
    errors = []
    
    for lead_id in request.lead_ids:
        try:
            pending_result = await db.execute(
                select(PendingLead).where(
                    PendingLead.id == lead_id,
                    PendingLead.tenant_id == tenant_id,
                )
            )
            pending = pending_result.scalar_one_or_none()
            
            if not pending:
                failed += 1
                errors.append({"lead_id": str(lead_id), "error": "Pending lead not found"})
                continue
            
            if request.action == "approve":
                # Auto-create contact and lead
                lead_data = pending.raw_data
                email = lead_data.get("email", "").lower()
                
                if not email:
                    failed += 1
                    errors.append({"lead_id": str(lead_id), "error": "No email in lead data"})
                    continue
                
                # Check/create contact
                contact_result = await db.execute(
                    select(Contact).where(Contact.tenant_id == tenant_id, Contact.email == email)
                )
                contact = contact_result.scalar_one_or_none()
                
                if not contact:
                    contact = Contact(
                        tenant_id=tenant_id,
                        first_name=lead_data.get("first_name", "") or pending.first_name or "",
                        last_name=lead_data.get("last_name", "") or pending.last_name or "",
                        email=email,
                        phone=lead_data.get("phone") or pending.phone,
                        title=lead_data.get("title") or pending.title,
                        company_name=lead_data.get("company_name") or pending.company_name,
                        source=pending.source,
                        utm_source=lead_data.get("utm_source", "firecrawl"),
                        utm_medium=lead_data.get("utm_medium", "organic"),
                        utm_campaign=lead_data.get("utm_campaign", pending.source),
                        custom_fields=lead_data.get("custom_fields", {}),
                        created_by_id=user.id,
                        updated_by_id=user.id,
                    )
                    db.add(contact)
                    await db.flush()
                
                # Create lead
                lead = Lead(
                    tenant_id=tenant_id,
                    contact_id=contact.id,
                    title=lead_data.get("title", f"Inbound from {pending.source}"),
                    status="new",
                    owner_id=user.id,
                    source=pending.source,
                    source_id=pending.source_id,
                    utm_source=lead_data.get("utm_source", "firecrawl"),
                    utm_medium=lead_data.get("utm_medium", "organic"),
                    utm_campaign=lead_data.get("utm_campaign", pending.source),
                    custom_fields=lead_data.get("custom_fields", {}),
                    created_by_id=user.id,
                    updated_by_id=user.id,
                )
                db.add(lead)
                await db.flush()
                
                # Update pending
                pending.status = PendingLeadStatusEnum.APPROVED
                pending.reviewed_by_id = user.id
                pending.reviewed_at = datetime.now(timezone.utc)
                pending.review_notes = request.reviewer_notes
                pending.created_lead_id = lead.id
                pending.created_contact_id = contact.id
                
                # Activity
                activity = Activity(
                    tenant_id=tenant_id,
                    lead_id=lead.id,
                    contact_id=contact.id,
                    type=ActivityTypeEnum.AI_ACTION,
                    subject=f"Lead approved from {pending.source}",
                    description=f"Lead imported from {pending.source} and approved by {user.full_name}",
                    user_id=user.id,
                    is_ai_generated=False,
                    metadata={"source": pending.source, "source_id": pending.source_id},
                )
                db.add(activity)
                
            else:
                # Reject
                pending.status = PendingLeadStatusEnum.REJECTED
                pending.reviewed_by_id = user.id
                pending.reviewed_at = datetime.now(timezone.utc)
                pending.review_notes = request.reviewer_notes
            
            if request.action == "approve":
                approved += 1
            else:
                rejected += 1
                
        except Exception as e:
            failed += 1
            errors.append({"lead_id": str(lead_id), "error": str(e)})
    
    await db.commit()
    
    return BulkLeadApprovalResponse(
        success=failed == 0,
        processed=approved + rejected,
        approved=approved,
        rejected=rejected,
        failed=failed,
        errors=errors,
    )


# Also add a general lead search endpoint that works with all integrations
@router.get("/search/integrations", response_model=List[FirecrawlSearchResult])
async def search_leads_all_integrations(
    query: str = Query(..., min_length=3),
    limit: int = Query(10, ge=1, le=50),
    source: Optional[str] = Query(None),
    current_user: tuple = Depends(require_leads_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Search leads across all connected integrations.
    """
    user, _ = current_user
    
    # Get all connected integrations
    query_filter = [
        Integration.tenant_id == tenant_id,
        Integration.status == IntegrationStatusEnum.CONNECTED,
    ]
    if source:
        query_filter.append(Integration.type == source)
    
    result = await db.execute(
        select(Integration).where(*query_filter)
    )
    integrations = result.scalars().all()
    
    all_leads = []
    integration_service = IntegrationService()
    
    for integration in integrations:
        if integration.type == "firecrawl":
            adapter = FirecrawlAdapter()
            credentials = integration.config.get("credentials", {})
            if not credentials.get("api_key"):
                continue
            
            from app.services.integration.firecrawl_adapter import FirecrawlSearchParams
            search_params = FirecrawlSearchParams(query=query, limit=limit)
            result = await adapter.search_leads(credentials, search_params)
            
            if result.success and result.leads:
                for lead in result.leads:
                    all_leads.append(FirecrawlSearchResult(
                        email=lead.email,
                        first_name=lead.first_name,
                        last_name=lead.last_name,
                        title=lead.title,
                        company_name=lead.company_name,
                        company_domain=lead.company_domain,
                        phone=lead.phone,
                        source=lead.source,
                        medium=lead.medium,
                        utm_source=lead.utm_source,
                        utm_medium=lead.utm_medium,
                        utm_campaign=lead.utm_campaign,
                        utm_content=lead.utm_content,
                        utm_term=lead.utm_term,
                        raw_data=lead.raw_data,
                        custom_fields=lead.custom_fields,
                    ))
    
    return all_leads[:limit]