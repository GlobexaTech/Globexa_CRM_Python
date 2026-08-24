"""
Companies API routes for Globexa CRM.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import get_current_active_user, require_contacts_read, require_contacts_write, get_tenant_id
from app.schemas import (
    CompanyCreate,
    CompanyUpdate,
    CompanyResponse,
    PaginationParams,
    PaginatedResponse,
)
from app.models import Company, Contact, User

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    data: CompanyCreate,
    current_user: tuple = Depends(require_contacts_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a new company."""
    user, _ = current_user
    
    # Check domain uniqueness if provided
    if data.domain:
        result = await db.execute(
            select(Company).where(Company.domain == data.domain, Company.tenant_id == tenant_id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Company with this domain already exists")
    
    company = Company(
        **data.model_dump(),
        tenant_id=tenant_id,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


@router.get("", response_model=PaginatedResponse)
async def list_companies(
    params: PaginationParams = Depends(),
    search: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    current_user: tuple = Depends(require_contacts_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List companies with filtering and pagination."""
    query = select(Company).where(Company.tenant_id == tenant_id)
    
    if search:
        query = query.where(
            or_(
                Company.name.ilike(f"%{search}%"),
                Company.domain.ilike(f"%{search}%"),
            )
        )
    if industry:
        query = query.where(Company.industry == industry)
    if source:
        query = query.where(Company.source == source)
    
    query = query.order_by(Company.name)
    
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)
    
    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    companies = result.scalars().all()
    
    return PaginatedResponse.create(
        items=[CompanyResponse.model_validate(c) for c in companies],
        total=total,
        params=params,
    )


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: UUID,
    current_user: tuple = Depends(require_contacts_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get a company by ID."""
    result = await db.execute(
        select(Company)
        .where(Company.id == company_id, Company.tenant_id == tenant_id)
        .options(selectinload(Company.contacts))
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: UUID,
    data: CompanyUpdate,
    current_user: tuple = Depends(require_contacts_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a company."""
    user, _ = current_user
    
    result = await db.execute(
        select(Company).where(Company.id == company_id, Company.tenant_id == tenant_id)
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Check domain uniqueness if changed
    if data.domain is not None and data.domain != company.domain:
        existing = await db.execute(
            select(Company).where(Company.domain == data.domain, Company.tenant_id == tenant_id, Company.id != company_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Company with this domain already exists")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(company, field, value)
    
    company.updated_by_id = user.id
    await db.commit()
    await db.refresh(company)
    return company


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: UUID,
    current_user: tuple = Depends(require_contacts_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete a company."""
    result = await db.execute(
        select(Company).where(Company.id == company_id, Company.tenant_id == tenant_id)
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    await db.delete(company)
    await db.commit()