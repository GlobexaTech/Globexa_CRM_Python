from datetime import datetime, timezone
from app.models import Deal
"""
Leads API routes for Globexa CRM.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import get_current_active_user, require_leads_read, require_leads_write, require_leads_assign, get_tenant_id
from app.schemas import (
    LeadCreate,
    LeadUpdate,
    LeadResponse,
    PaginationParams,
    PaginatedResponse,
)
from app.models import Lead, Contact, Company, User, Pipeline, Stage, LeadStatusEnum

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    data: LeadCreate,
    current_user: tuple = Depends(require_leads_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a new lead."""
    user, _ = current_user
    
    # Verify contact exists if provided
    if data.contact_id:
        result = await db.execute(
            select(Contact).where(Contact.id == data.contact_id, Contact.tenant_id == tenant_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Contact not found")
    
    # Verify company exists if provided
    if data.company_id:
        result = await db.execute(
            select(Company).where(Company.id == data.company_id, Company.tenant_id == tenant_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Company not found")
    
    # Verify owner exists if provided
    if data.owner_id:
        from app.models import Membership
        result = await db.execute(
            select(Membership).where(Membership.user_id == data.owner_id, Membership.tenant_id == tenant_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Owner not found in this tenant")
    
    lead = Lead(
        **data.model_dump(),
        tenant_id=tenant_id,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


@router.get("", response_model=PaginatedResponse)
async def list_leads(
    params: PaginationParams = Depends(),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    owner_id: Optional[UUID] = Query(None),
    source: Optional[str] = Query(None),
    is_qualified: Optional[bool] = Query(None),
    current_user: tuple = Depends(require_leads_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List leads with filtering and pagination."""
    user, membership = current_user
    
    query = select(Lead).where(Lead.tenant_id == tenant_id).options(
        selectinload(Lead.owner),
        selectinload(Lead.contact),
        selectinload(Lead.company),
    )
    
    # Sales executives only see their assigned leads
    if membership.role.value == "sales_executive":
        query = query.where(Lead.owner_id == user.id)
    
    if search:
        query = query.where(
            or_(
                Lead.title.ilike(f"%{search}%"),
                Lead.description.ilike(f"%{search}%"),
            )
        )
    if status:
        query = query.where(Lead.status == status)
    if owner_id:
        query = query.where(Lead.owner_id == owner_id)
    if source:
        query = query.where(Lead.source == source)
    if is_qualified is not None:
        query = query.where(Lead.is_qualified == is_qualified)
    
    query = query.order_by(Lead.created_at.desc())
    
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)
    
    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    leads = result.scalars().all()
    
    return PaginatedResponse.create(
        items=[LeadResponse.model_validate(l) for l in leads],
        total=total,
        params=params,
    )


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: UUID,
    current_user: tuple = Depends(require_leads_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get a lead by ID."""
    user, membership = current_user
    
    query = select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id).options(
        selectinload(Lead.owner),
        selectinload(Lead.contact).selectinload(Contact.company),
        selectinload(Lead.company),
    )
    
    # Sales executives only see their assigned leads
    if membership.role.value == "sales_executive":
        query = query.where(Lead.owner_id == user.id)
    
    result = await db.execute(query)
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: UUID,
    data: LeadUpdate,
    current_user: tuple = Depends(require_leads_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a lead."""
    user, membership = current_user
    
    query = select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
    
    # Sales executives can only update their assigned leads
    if membership.role.value == "sales_executive":
        query = query.where(Lead.owner_id == user.id)
    
    result = await db.execute(query)
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Verify relations if provided
    update_data = data.model_dump(exclude_unset=True)
    
    if "contact_id" in update_data and update_data["contact_id"]:
        result = await db.execute(
            select(Contact).where(Contact.id == update_data["contact_id"], Contact.tenant_id == tenant_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Contact not found")
    
    if "company_id" in update_data and update_data["company_id"]:
        result = await db.execute(
            select(Company).where(Company.id == update_data["company_id"], Company.tenant_id == tenant_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Company not found")
    
    if "owner_id" in update_data and update_data["owner_id"]:
        from app.models import Membership
        result = await db.execute(
            select(Membership).where(Membership.user_id == update_data["owner_id"], Membership.tenant_id == tenant_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Owner not found in this tenant")
        
        # Set assignment metadata
        lead.assigned_by_id = user.id
        lead.assigned_at = datetime.now(timezone.utc)
    
    for field, value in update_data.items():
        setattr(lead, field, value)
    
    lead.updated_by_id = user.id
    await db.commit()
    await db.refresh(lead)
    return lead


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: UUID,
    current_user: tuple = Depends(require_leads_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete a lead."""
    user, membership = current_user
    
    query = select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
    
    # Sales executives can only delete their assigned leads
    if membership.role.value == "sales_executive":
        query = query.where(Lead.owner_id == user.id)
    
    result = await db.execute(query)
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    await db.delete(lead)
    await db.commit()


# Lead assignment endpoint
@router.post("/{lead_id}/assign", response_model=LeadResponse)
async def assign_lead(
    lead_id: UUID,
    owner_id: UUID,
    current_user: tuple = Depends(require_leads_assign),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Assign a lead to a user."""
    user, membership = current_user
    
    query = select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
    
    # Sales executives can only assign their own leads (or managers can assign any)
    if membership.role.value == "sales_executive":
        query = query.where(Lead.owner_id == user.id)
    
    result = await db.execute(query)
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Verify new owner exists in tenant
    from app.models import Membership
    result = await db.execute(
        select(Membership).where(Membership.user_id == owner_id, Membership.tenant_id == tenant_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found in this tenant")
    
    lead.owner_id = owner_id
    lead.assigned_by_id = user.id
    lead.assigned_at = datetime.now(timezone.utc)
    lead.updated_by_id = user.id
    
    await db.commit()
    await db.refresh(lead)
    return lead


# Lead qualification endpoint
@router.post("/{lead_id}/qualify", response_model=LeadResponse)
async def qualify_lead(
    lead_id: UUID,
    qualification_notes: Optional[str] = None,
    current_user: tuple = Depends(require_leads_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Mark a lead as qualified."""
    from datetime import datetime, timezone
    user, membership = current_user
    
    query = select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
    
    if membership.role.value == "sales_executive":
        query = query.where(Lead.owner_id == user.id)
    
    result = await db.execute(query)
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    lead.is_qualified = True
    lead.status = LeadStatusEnum.QUALIFIED
    lead.qualified_by_id = user.id
    lead.qualified_at = datetime.now(timezone.utc)
    if qualification_notes:
        lead.qualification_notes = qualification_notes
    lead.updated_by_id = user.id
    
    await db.commit()
    await db.refresh(lead)
    return lead


# Lead conversion endpoint
@router.post("/{lead_id}/convert", response_model=LeadResponse)
async def convert_lead(
    lead_id: UUID,
    deal_title: str,
    pipeline_id: UUID,
    stage_id: UUID,
    value: int = 0,
    current_user: tuple = Depends(require_leads_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Convert a lead to a deal."""
    from datetime import datetime, timezone
    user, membership = current_user
    
    query = select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
    
    if membership.role.value == "sales_executive":
        query = query.where(Lead.owner_id == user.id)
    
    result = await db.execute(query)
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Verify pipeline and stage
    result = await db.execute(
        select(Pipeline).where(Pipeline.id == pipeline_id, Pipeline.tenant_id == tenant_id)
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    result = await db.execute(
        select(Stage).where(Stage.id == stage_id, Stage.pipeline_id == pipeline_id)
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    
    # Create deal
    deal = Deal(
        tenant_id=tenant_id,
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        contact_id=lead.contact_id,
        company_id=lead.company_id,
        lead_id=lead.id,
        title=deal_title,
        value=value,
        currency="USD",
        owner_id=lead.owner_id,
        probability=stage.probability,
        source=lead.source,
        custom_fields={},
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(deal)
    await db.flush()
    
    # Update lead
    lead.status = LeadStatusEnum.CONVERTED
    lead.converted_at = datetime.now(timezone.utc)
    lead.converted_deal_id = deal.id
    lead.updated_by_id = user.id
    
    await db.commit()
    await db.refresh(lead)
    return lead