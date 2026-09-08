"""
Contacts API routes for Globexa CRM.
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
    ContactCreate,
    ContactUpdate,
    ContactResponse,
    PaginationParams,
    PaginatedResponse,
)
from app.models import Contact, Company, User

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    data: ContactCreate,
    current_user: tuple = Depends(require_contacts_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a new contact."""
    user, _ = current_user
    
    # Verify company exists if provided
    if data.company_id:
        result = await db.execute(
            select(Company).where(Company.id == data.company_id, Company.tenant_id == tenant_id)
        )
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
    
    contact = Contact(
        **data.model_dump(),
        tenant_id=tenant_id,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    await db.refresh(contact, attribute_names=["company"])
    return ContactResponse.model_validate(contact)


@router.get("", response_model=PaginatedResponse)
async def list_contacts(
    params: PaginationParams = Depends(),
    search: Optional[str] = Query(None),
    company_id: Optional[UUID] = Query(None),
    is_primary: Optional[bool] = Query(None),
    email_opted_out: Optional[bool] = Query(None),
    current_user: tuple = Depends(require_contacts_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List contacts with filtering and pagination."""
    query = select(Contact).where(Contact.tenant_id == tenant_id).options(selectinload(Contact.company))
    
    if search:
        query = query.where(
            or_(
                Contact.first_name.ilike(f"%{search}%"),
                Contact.last_name.ilike(f"%{search}%"),
                Contact.email.ilike(f"%{search}%"),
            )
        )
    if company_id:
        query = query.where(Contact.company_id == company_id)
    if is_primary is not None:
        query = query.where(Contact.is_primary == is_primary)
    if email_opted_out is not None:
        query = query.where(Contact.email_opted_out == email_opted_out)
    
    query = query.order_by(Contact.last_name, Contact.first_name)
    
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)
    
    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    contacts = result.scalars().all()
    
    return PaginatedResponse.create(
        items=[ContactResponse.model_validate(c) for c in contacts],
        total=total,
        params=params,
    )


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: UUID,
    current_user: tuple = Depends(require_contacts_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get a contact by ID."""
    result = await db.execute(
        select(Contact)
        .where(Contact.id == contact_id, Contact.tenant_id == tenant_id)
        .options(selectinload(Contact.company))
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.refresh(contact)
    await db.refresh(contact, attribute_names=["company"])
    return ContactResponse.model_validate(contact)


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: UUID,
    data: ContactUpdate,
    current_user: tuple = Depends(require_contacts_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a contact."""
    user, _ = current_user
    
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.tenant_id == tenant_id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    # Verify company if provided
    if data.company_id is not None:
        if data.company_id:
            result = await db.execute(
                select(Company).where(Company.id == data.company_id, Company.tenant_id == tenant_id)
            )
            company = result.scalar_one_or_none()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contact, field, value)
    
    contact.updated_by_id = user.id
    await db.commit()
    await db.refresh(contact)
    await db.refresh(contact, attribute_names=["company"])
    return ContactResponse.model_validate(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: UUID,
    current_user: tuple = Depends(require_contacts_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete a contact."""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.tenant_id == tenant_id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    await db.delete(contact)
    await db.commit()
