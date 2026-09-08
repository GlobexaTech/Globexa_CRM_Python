"""
Tasks, Notes, Activities API routes for Globexa CRM.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import require_permission
from app.services.crm.serialization import scalar_response
from app.api.deps import get_current_active_user, get_tenant_id, require_deals_read, require_deals_write, require_contacts_read, require_contacts_write, require_leads_read, require_leads_write
from app.schemas import (
    TaskCreate,
    TaskUpdate,
    TaskResponse,
    NoteCreate,
    NoteUpdate,
    NoteResponse,
    ActivityResponse,
    PaginationParams,
    PaginatedResponse,
)
from app.models import Task, Note, Activity, Lead, Deal, Contact, Company, User, TaskStatusEnum, TaskPriorityEnum

# Tasks router
tasks_router = APIRouter(prefix="/tasks", tags=["Tasks"])


@tasks_router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    current_user: tuple = Depends(require_permission("tasks:write")),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a new task."""
    user, _ = current_user
    
    # Verify at least one relation is provided
    if not any([data.lead_id, data.deal_id, data.contact_id, data.company_id]):
        raise HTTPException(status_code=400, detail="At least one of lead_id, deal_id, contact_id, or company_id is required")
    
    # Verify relations
    if data.lead_id:
        result = await db.execute(select(Lead).where(Lead.id == data.lead_id, Lead.tenant_id == tenant_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Lead not found")
    
    if data.deal_id:
        result = await db.execute(select(Deal).where(Deal.id == data.deal_id, Deal.tenant_id == tenant_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Deal not found")
    
    if data.contact_id:
        result = await db.execute(select(Contact).where(Contact.id == data.contact_id, Contact.tenant_id == tenant_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Contact not found")
    
    if data.company_id:
        result = await db.execute(select(Company).where(Company.id == data.company_id, Company.tenant_id == tenant_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Company not found")
    
    if data.owner_id:
        from app.models import Membership
        result = await db.execute(select(Membership).where(Membership.user_id == data.owner_id, Membership.tenant_id == tenant_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Owner not found in this tenant")
    
    values = data.model_dump()
    values["owner_id"] = values.get("owner_id") or user.id
    task = Task(
        **values,
        tenant_id=tenant_id,
        created_by_id=user.id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return scalar_response(TaskResponse, task)


@tasks_router.get("", response_model=PaginatedResponse)
async def list_tasks(
    params: PaginationParams = Depends(),
    status: Optional[str] = Query(None),
    owner_id: Optional[UUID] = Query(None),
    lead_id: Optional[UUID] = Query(None),
    deal_id: Optional[UUID] = Query(None),
    overdue: Optional[bool] = Query(None),
    current_user: tuple = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List tasks with filtering."""
    user, membership = current_user
    
    query = select(Task).where(Task.tenant_id == tenant_id).options(
        selectinload(Task.owner),
        selectinload(Task.lead),
        selectinload(Task.deal),
    )
    
    # Sales executives only see their tasks
    if membership.role.value == "sales_executive":
        query = query.where(Task.owner_id == user.id)
    
    if status:
        query = query.where(Task.status == status)
    if owner_id:
        query = query.where(Task.owner_id == owner_id)
    if lead_id:
        query = query.where(Task.lead_id == lead_id)
    if deal_id:
        query = query.where(Task.deal_id == deal_id)
    if overdue:
        from datetime import datetime, timezone
        query = query.where(
            Task.due_date < datetime.now(timezone.utc),
            Task.status != TaskStatusEnum.COMPLETED,
        )
    
    query = query.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())
    
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)
    
    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    tasks = result.scalars().all()
    
    return PaginatedResponse.create(
        items=[scalar_response(TaskResponse, t) for t in tasks],
        total=total,
        params=params,
    )


@tasks_router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    current_user: tuple = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get a task by ID."""
    user, membership = current_user
    
    query = select(Task).where(Task.id == task_id, Task.tenant_id == tenant_id).options(
        selectinload(Task.owner),
        selectinload(Task.lead),
        selectinload(Task.deal),
    )
    
    if membership.role.value == "sales_executive":
        query = query.where(Task.owner_id == user.id)
    
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return scalar_response(TaskResponse, task)


@tasks_router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    data: TaskUpdate,
    current_user: tuple = Depends(require_permission("tasks:write")),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a task."""
    user, membership = current_user
    
    query = select(Task).where(Task.id == task_id, Task.tenant_id == tenant_id)
    
    if membership.role.value == "sales_executive":
        query = query.where(Task.owner_id == user.id)
    
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    update_data = data.model_dump(exclude_unset=True)
    
    # Handle completion
    if "status" in update_data and update_data["status"] == TaskStatusEnum.COMPLETED:
        if not task.completed_at:
            from datetime import datetime, timezone
            task.completed_at = datetime.now(timezone.utc)
    
    # Verify owner if provided
    if "owner_id" in update_data and update_data["owner_id"]:
        from app.models import Membership
        result = await db.execute(
            select(Membership).where(Membership.user_id == update_data["owner_id"], Membership.tenant_id == tenant_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Owner not found in this tenant")
    
    for field, value in update_data.items():
        setattr(task, field, value)
    
    await db.commit()
    await db.refresh(task)
    return scalar_response(TaskResponse, task)


@tasks_router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    current_user: tuple = Depends(require_permission("tasks:delete")),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete a task."""
    user, membership = current_user
    
    query = select(Task).where(Task.id == task_id, Task.tenant_id == tenant_id)
    
    if membership.role.value == "sales_executive":
        query = query.where(Task.owner_id == user.id)
    
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    await db.delete(task)
    await db.commit()


# Notes router
notes_router = APIRouter(prefix="/notes", tags=["Notes"])


@notes_router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    data: NoteCreate,
    current_user: tuple = Depends(require_permission("notes:write")),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a new note."""
    user, _ = current_user
    
    # Verify at least one relation is provided
    if not any([data.lead_id, data.deal_id, data.contact_id, data.company_id]):
        raise HTTPException(status_code=400, detail="At least one of lead_id, deal_id, contact_id, or company_id is required")
    
    # Verify relations
    if data.lead_id:
        result = await db.execute(select(Lead).where(Lead.id == data.lead_id, Lead.tenant_id == tenant_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Lead not found")
    
    if data.deal_id:
        result = await db.execute(select(Deal).where(Deal.id == data.deal_id, Deal.tenant_id == tenant_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Deal not found")
    
    if data.contact_id:
        result = await db.execute(select(Contact).where(Contact.id == data.contact_id, Contact.tenant_id == tenant_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Contact not found")
    
    if data.company_id:
        result = await db.execute(select(Company).where(Company.id == data.company_id, Company.tenant_id == tenant_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Company not found")
    
    note = Note(
        **data.model_dump(),
        tenant_id=tenant_id,
        author_id=user.id,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


@notes_router.get("", response_model=PaginatedResponse)
async def list_notes(
    params: PaginationParams = Depends(),
    lead_id: Optional[UUID] = Query(None),
    deal_id: Optional[UUID] = Query(None),
    contact_id: Optional[UUID] = Query(None),
    company_id: Optional[UUID] = Query(None),
    current_user: tuple = Depends(require_permission("notes:read")),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List notes with filtering."""
    query = select(Note).where(Note.tenant_id == tenant_id).options(selectinload(Note.author))
    
    if lead_id:
        query = query.where(Note.lead_id == lead_id)
    if deal_id:
        query = query.where(Note.deal_id == deal_id)
    if contact_id:
        query = query.where(Note.contact_id == contact_id)
    if company_id:
        query = query.where(Note.company_id == company_id)
    
    query = query.order_by(Note.is_pinned.desc(), Note.created_at.desc())
    
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)
    
    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    notes = result.scalars().all()
    
    return PaginatedResponse.create(
        items=[NoteResponse.model_validate(n) for n in notes],
        total=total,
        params=params,
    )


@notes_router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: UUID,
    current_user: tuple = Depends(require_permission("notes:read")),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get a note by ID."""
    result = await db.execute(
        select(Note)
        .where(Note.id == note_id, Note.tenant_id == tenant_id)
        .options(selectinload(Note.author))
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@notes_router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: UUID,
    data: NoteUpdate,
    current_user: tuple = Depends(require_permission("notes:write")),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a note."""
    user, membership = current_user
    
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.tenant_id == tenant_id)
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Only author or admin/owner can update
    if note.author_id != user.id and membership.role.value not in ["admin", "owner"]:
        raise HTTPException(status_code=403, detail="Not authorized to update this note")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)
    
    await db.commit()
    await db.refresh(note)
    return note


@notes_router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: UUID,
    current_user: tuple = Depends(require_permission("notes:write")),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete a note."""
    user, membership = current_user
    
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.tenant_id == tenant_id)
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Only author or admin/owner can delete
    if note.author_id != user.id and membership.role.value not in ["admin", "owner"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete this note")
    
    await db.delete(note)
    await db.commit()


# Activities router
activities_router = APIRouter(prefix="/activities", tags=["Activities"])


@activities_router.get("", response_model=PaginatedResponse)
async def list_activities(
    params: PaginationParams = Depends(),
    lead_id: Optional[UUID] = Query(None),
    deal_id: Optional[UUID] = Query(None),
    contact_id: Optional[UUID] = Query(None),
    company_id: Optional[UUID] = Query(None),
    type: Optional[str] = Query(None),
    user_id: Optional[UUID] = Query(None),
    current_user: tuple = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List activities (timeline) with filtering."""
    query = select(Activity).where(Activity.tenant_id == tenant_id).options(selectinload(Activity.user))
    
    if lead_id:
        query = query.where(Activity.lead_id == lead_id)
    if deal_id:
        query = query.where(Activity.deal_id == deal_id)
    if contact_id:
        query = query.where(Activity.contact_id == contact_id)
    if company_id:
        query = query.where(Activity.company_id == company_id)
    if type:
        query = query.where(Activity.type == type)
    if user_id:
        query = query.where(Activity.user_id == user_id)
    
    query = query.order_by(Activity.created_at.desc())
    
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)
    
    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    activities = result.scalars().all()
    
    return PaginatedResponse.create(
        items=[ActivityResponse.model_validate(a) for a in activities],
        total=total,
        params=params,
    )
