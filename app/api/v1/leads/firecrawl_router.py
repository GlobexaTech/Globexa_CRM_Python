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


async def firecrawl_credentials(db, tenant_id, integration_id):
    import json
    from app.models import IntegrationCredential
    row = await db.scalar(select(IntegrationCredential).where(
        IntegrationCredential.tenant_id == tenant_id, IntegrationCredential.integration_id == integration_id,
        IntegrationCredential.is_active.is_(True),
    ).order_by(IntegrationCredential.created_at.desc()).limit(1))
    if not row or (row.token_expires_at and row.token_expires_at <= datetime.now(timezone.utc)):
        raise HTTPException(409, "Active Firecrawl credentials are required")
    return json.loads(row.credentials_encrypted)


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
    
    # Resolve only the tenant integration's active encrypted credential.
    credentials = await firecrawl_credentials(db, tenant_id, integration.id)
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
            error_message="Firecrawl search failed",
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
    status: Optional[PendingLeadStatusEnum] = Query(None),
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
    from app.services.crm.lead_review import review
    result = await review(db, tenant_id, current_user[0].id, request.source, request.source_id,
                          request.action, request.lead_data, request.reviewer_notes)
    await db.commit()
    return result


@router.post("/bulk-approve", response_model=BulkLeadApprovalResponse)
async def bulk_approve_leads(
    request: BulkLeadApprovalRequest,
    current_user: tuple = Depends(require_leads_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    from app.services.crm.lead_review import review
    if request.action not in {"approve", "reject"}:
        raise HTTPException(422, "Invalid bulk review action")
    approved = rejected = 0
    errors = []
    for lead_id in dict.fromkeys(request.lead_ids):
        try:
            async with db.begin_nested():
                pending = await db.scalar(select(PendingLead).where(
                    PendingLead.id == lead_id, PendingLead.tenant_id == tenant_id))
                if pending is None:
                    raise HTTPException(404, "Pending lead not found")
                await review(db, tenant_id, current_user[0].id, pending.source, pending.source_id,
                             request.action, {}, request.reviewer_notes)
            if request.action == "approve":
                approved += 1
            else:
                rejected += 1
        except HTTPException as exc:
            errors.append({"lead_id": str(lead_id), "error": exc.detail})
    await db.commit()
    return BulkLeadApprovalResponse(success=not errors, processed=approved + rejected,
                                    approved=approved, rejected=rejected, failed=len(errors), errors=errors)


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
            credentials = await firecrawl_credentials(db, tenant_id, integration.id)
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