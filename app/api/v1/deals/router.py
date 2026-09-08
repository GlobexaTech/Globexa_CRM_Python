"""
Deals API routes for Globexa CRM.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field
from app.core.rbac import Permission
from app.api.deps import require_permission

from app.core.database import get_db
from app.services.crm.serialization import scalar_response
from app.api.deps import get_current_active_user, require_deals_read, require_deals_write, get_tenant_id
from app.schemas import (
    DealCreate,
    DealUpdate,
    DealResponse,
    PipelineCreate,
    PipelineUpdate,
    PipelineResponse,
    StageCreate,
    StageUpdate,
    StageResponse,
    PaginationParams,
    PaginatedResponse,
)
from app.models import Deal, Pipeline, Stage, Contact, Company, User

router = APIRouter(prefix="/deals", tags=["Deals"])
require_pipeline_manage = require_permission(Permission.DEALS_PIPELINE_MANAGE)


class StageOrderInput(BaseModel):
    stage_ids: list[UUID] = Field(min_length=1, max_length=100)


@router.put("/pipelines/{pipeline_id}/stages/order", response_model=List[StageResponse])
async def reorder_stages(
    pipeline_id: UUID,
    data: StageOrderInput,
    current_user: tuple = Depends(require_pipeline_manage),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Atomically reorder all stages after validating the exact tenant stage set."""
    pipeline = await db.scalar(select(Pipeline).where(
        Pipeline.id == pipeline_id, Pipeline.tenant_id == tenant_id
    ).with_for_update())
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    stages = (await db.scalars(select(Stage).where(
        Stage.pipeline_id == pipeline_id, Stage.tenant_id == tenant_id
    ).with_for_update())).all()
    if len(data.stage_ids) != len(set(data.stage_ids)) or set(data.stage_ids) != {s.id for s in stages}:
        raise HTTPException(422, "Provide every pipeline stage exactly once")
    by_id = {stage.id: stage for stage in stages}
    # Separate temporary positions preserve uniqueness if a deployment adds an index.
    temporary = max((stage.order for stage in stages), default=0) + len(stages) + 1
    for index, stage in enumerate(stages):
        stage.order = temporary + index
    await db.flush()
    for index, stage_id in enumerate(data.stage_ids):
        by_id[stage_id].order = index
    await db.flush()
    for stage in stages:
        await db.refresh(stage)
    response = [StageResponse.model_validate(by_id[stage_id]) for stage_id in data.stage_ids]
    await db.commit()
    return response


# Pipeline endpoints
@router.post("/pipelines", response_model=PipelineResponse, status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    data: PipelineCreate,
    current_user: tuple = Depends(require_pipeline_manage),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a new pipeline."""
    user, _ = current_user
    
    # If setting as default, unset other defaults
    if data.is_default:
        result = await db.execute(
            select(Pipeline).where(Pipeline.tenant_id == tenant_id, Pipeline.is_default == True)
        )
        existing_default = result.scalar_one_or_none()
        if existing_default:
            existing_default.is_default = False
    
    pipeline = Pipeline(
        **data.model_dump(),
        tenant_id=tenant_id,
    )
    db.add(pipeline)
    await db.commit()
    await db.refresh(pipeline)
    await db.refresh(pipeline, attribute_names=["stages"])
    return PipelineResponse.model_validate(pipeline)


@router.get("/pipelines", response_model=List[PipelineResponse])
async def list_pipelines(
    current_user: tuple = Depends(require_deals_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List all pipelines for the tenant."""
    result = await db.execute(
        select(Pipeline)
        .where(Pipeline.tenant_id == tenant_id)
        .options(selectinload(Pipeline.stages))
        .order_by(Pipeline.is_default.desc(), Pipeline.name)
    )
    pipelines = result.scalars().all()
    return [PipelineResponse.model_validate(p) for p in pipelines]


@router.get("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def get_pipeline(
    pipeline_id: UUID,
    current_user: tuple = Depends(require_deals_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get a pipeline by ID with stages."""
    result = await db.execute(
        select(Pipeline)
        .where(Pipeline.id == pipeline_id, Pipeline.tenant_id == tenant_id)
        .options(selectinload(Pipeline.stages))
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return pipeline


@router.patch("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def update_pipeline(
    pipeline_id: UUID,
    data: PipelineUpdate,
    current_user: tuple = Depends(require_pipeline_manage),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a pipeline."""
    user, _ = current_user
    
    result = await db.execute(
        select(Pipeline).where(Pipeline.id == pipeline_id, Pipeline.tenant_id == tenant_id)
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    update_data = data.model_dump(exclude_unset=True)
    
    if "is_default" in update_data and update_data["is_default"]:
        # Unset other defaults
        result = await db.execute(
            select(Pipeline).where(Pipeline.tenant_id == tenant_id, Pipeline.is_default == True, Pipeline.id != pipeline_id)
        )
        existing_default = result.scalar_one_or_none()
        if existing_default:
            existing_default.is_default = False
    
    for field, value in update_data.items():
        setattr(pipeline, field, value)
    
    await db.commit()
    await db.refresh(pipeline)
    await db.refresh(pipeline, attribute_names=["stages"])
    return PipelineResponse.model_validate(pipeline)


@router.delete("/pipelines/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline(
    pipeline_id: UUID,
    current_user: tuple = Depends(require_pipeline_manage),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete a pipeline."""
    result = await db.execute(
        select(Pipeline).where(Pipeline.id == pipeline_id, Pipeline.tenant_id == tenant_id)
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    # Check if pipeline has deals
    result = await db.execute(
        select(func.count()).select_from(Deal).where(Deal.pipeline_id == pipeline_id)
    )
    if result.scalar() > 0:
        raise HTTPException(status_code=400, detail="Cannot delete pipeline with existing deals")
    
    await db.delete(pipeline)
    await db.commit()


# Stage endpoints
@router.post("/pipelines/{pipeline_id}/stages", response_model=StageResponse, status_code=status.HTTP_201_CREATED)
async def create_stage(
    pipeline_id: UUID,
    data: StageCreate,
    current_user: tuple = Depends(require_pipeline_manage),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a new stage in a pipeline."""
    # Verify pipeline exists
    result = await db.execute(
        select(Pipeline).where(Pipeline.id == pipeline_id, Pipeline.tenant_id == tenant_id)
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    if data.pipeline_id != pipeline_id:
        raise HTTPException(422, "Stage pipeline must match the URL")

    # Check order uniqueness
    result = await db.execute(
        select(Stage).where(Stage.pipeline_id == pipeline_id, Stage.order == data.order)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Stage with this order already exists")
    
    stage = Stage(
        **data.model_dump(exclude={"pipeline_id"}),
        tenant_id=tenant_id,
        pipeline_id=pipeline_id,
    )
    db.add(stage)
    await db.commit()
    await db.refresh(stage)
    return stage


@router.get("/pipelines/{pipeline_id}/stages", response_model=List[StageResponse])
async def list_stages(
    pipeline_id: UUID,
    current_user: tuple = Depends(require_deals_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List all stages in a pipeline."""
    result = await db.execute(
        select(Stage)
        .where(Stage.pipeline_id == pipeline_id, Stage.tenant_id == tenant_id)
        .order_by(Stage.order)
    )
    stages = result.scalars().all()
    return [StageResponse.model_validate(s) for s in stages]


@router.patch("/stages/{stage_id}", response_model=StageResponse)
async def update_stage(
    stage_id: UUID,
    data: StageUpdate,
    current_user: tuple = Depends(require_pipeline_manage),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a stage."""
    result = await db.execute(
        select(Stage).where(Stage.id == stage_id, Stage.tenant_id == tenant_id)
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    
    update_data = data.model_dump(exclude_unset=True)
    
    if "order" in update_data:
        # Check order uniqueness
        result = await db.execute(
            select(Stage).where(Stage.pipeline_id == stage.pipeline_id, Stage.order == update_data["order"], Stage.id != stage_id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Stage with this order already exists")
    
    for field, value in update_data.items():
        setattr(stage, field, value)
    
    await db.commit()
    await db.refresh(stage)
    return stage


@router.delete("/stages/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stage(
    stage_id: UUID,
    current_user: tuple = Depends(require_pipeline_manage),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete a stage."""
    result = await db.execute(
        select(Stage).where(Stage.id == stage_id, Stage.tenant_id == tenant_id)
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    
    # Check if stage has deals
    result = await db.execute(
        select(func.count()).select_from(Deal).where(Deal.stage_id == stage_id)
    )
    if result.scalar() > 0:
        raise HTTPException(status_code=400, detail="Cannot delete stage with existing deals")
    
    await db.delete(stage)
    await db.commit()


# Deal endpoints
@router.post("", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
async def create_deal(
    data: DealCreate,
    current_user: tuple = Depends(require_deals_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a new deal."""
    user, _ = current_user
    
    # Verify pipeline and stage
    result = await db.execute(
        select(Pipeline).where(Pipeline.id == data.pipeline_id, Pipeline.tenant_id == tenant_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    result = await db.execute(
        select(Stage).where(Stage.id == data.stage_id, Stage.pipeline_id == data.pipeline_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Stage not found")
    
    # Verify contact if provided
    if data.contact_id:
        result = await db.execute(
            select(Contact).where(Contact.id == data.contact_id, Contact.tenant_id == tenant_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Contact not found")
    
    # Verify company if provided
    if data.company_id:
        result = await db.execute(
            select(Company).where(Company.id == data.company_id, Company.tenant_id == tenant_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Company not found")
    
    # Verify lead if provided
    if data.lead_id:
        result = await db.execute(
            select(Deal).where(Deal.lead_id == data.lead_id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Lead already converted to a deal")
    
    # Verify owner if provided
    if data.owner_id:
        from app.models import Membership
        result = await db.execute(
            select(Membership).where(Membership.user_id == data.owner_id, Membership.tenant_id == tenant_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Owner not found in this tenant")
    
    # Set weighted value
    stage = await db.get(Stage, data.stage_id)
    weighted_value = int(data.value * stage.probability / 100) if stage else 0
    
    deal = Deal(
        **data.model_dump(),
        tenant_id=tenant_id,
        weighted_value=weighted_value,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    return scalar_response(DealResponse, deal)


@router.get("", response_model=PaginatedResponse)
async def list_deals(
    params: PaginationParams = Depends(),
    search: Optional[str] = Query(None),
    pipeline_id: Optional[UUID] = Query(None),
    stage_id: Optional[UUID] = Query(None),
    owner_id: Optional[UUID] = Query(None),
    current_user: tuple = Depends(require_deals_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List deals with filtering and pagination."""
    user, membership = current_user
    
    query = select(Deal).where(Deal.tenant_id == tenant_id).options(
        selectinload(Deal.owner),
        selectinload(Deal.contact).selectinload(Contact.company),
        selectinload(Deal.company),
        selectinload(Deal.stage),
        selectinload(Deal.pipeline),
    )
    
    # Sales executives only see their deals
    if membership.role.value == "sales_executive":
        query = query.where(Deal.owner_id == user.id)
    
    if search:
        query = query.where(
            or_(
                Deal.title.ilike(f"%{search}%"),
                Deal.description.ilike(f"%{search}%"),
            )
        )
    if pipeline_id:
        query = query.where(Deal.pipeline_id == pipeline_id)
    if stage_id:
        query = query.where(Deal.stage_id == stage_id)
    if owner_id:
        query = query.where(Deal.owner_id == owner_id)
    
    query = query.order_by(Deal.expected_close_date.asc().nullslast(), Deal.created_at.desc())
    
    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)
    
    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    deals = result.scalars().all()
    
    return PaginatedResponse.create(
        items=[scalar_response(DealResponse, d) for d in deals],
        total=total,
        params=params,
    )


@router.get("/{deal_id}", response_model=DealResponse)
async def get_deal(
    deal_id: UUID,
    current_user: tuple = Depends(require_deals_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get a deal by ID."""
    user, membership = current_user
    
    query = select(Deal).where(Deal.id == deal_id, Deal.tenant_id == tenant_id).options(
        selectinload(Deal.owner),
        selectinload(Deal.contact).selectinload(Contact.company),
        selectinload(Deal.company),
        selectinload(Deal.stage),
        selectinload(Deal.pipeline),
        selectinload(Deal.proposals),
    )
    
    if membership.role.value == "sales_executive":
        query = query.where(Deal.owner_id == user.id)
    
    result = await db.execute(query)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return scalar_response(DealResponse, deal)


@router.patch("/{deal_id}", response_model=DealResponse)
async def update_deal(
    deal_id: UUID,
    data: DealUpdate,
    current_user: tuple = Depends(require_deals_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update a deal."""
    user, membership = current_user
    
    query = select(Deal).where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
    
    if membership.role.value == "sales_executive":
        query = query.where(Deal.owner_id == user.id)
    
    result = await db.execute(query)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    
    update_data = data.model_dump(exclude_unset=True)
    
    # Verify relations
    if "pipeline_id" in update_data:
        result = await db.execute(
            select(Pipeline).where(Pipeline.id == update_data["pipeline_id"], Pipeline.tenant_id == tenant_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Pipeline not found")
    
    if "stage_id" in update_data:
        result = await db.execute(
            select(Stage).where(Stage.id == update_data["stage_id"])
        )
        stage = result.scalar_one_or_none()
        if not stage:
            raise HTTPException(status_code=404, detail="Stage not found")
        if "pipeline_id" in update_data and stage.pipeline_id != update_data["pipeline_id"]:
            raise HTTPException(status_code=400, detail="Stage does not belong to the specified pipeline")
        elif "pipeline_id" not in update_data and stage.pipeline_id != deal.pipeline_id:
            raise HTTPException(status_code=400, detail="Stage does not belong to the deal's pipeline")
    
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
    
    # Update weighted value if value or stage changed
    if "value" in update_data or "stage_id" in update_data:
        value = update_data.get("value", deal.value)
        stage_id = update_data.get("stage_id", deal.stage_id)
        stage = await db.get(Stage, stage_id)
        if stage:
            deal.weighted_value = int(value * stage.probability / 100)
    
    for field, value in update_data.items():
        setattr(deal, field, value)
    
    deal.updated_by_id = user.id
    await db.commit()
    await db.refresh(deal)
    return scalar_response(DealResponse, deal)


@router.delete("/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deal(
    deal_id: UUID,
    current_user: tuple = Depends(require_deals_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete a deal."""
    user, membership = current_user
    
    query = select(Deal).where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
    
    if membership.role.value == "sales_executive":
        query = query.where(Deal.owner_id == user.id)
    
    result = await db.execute(query)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    
    await db.delete(deal)
    await db.commit()


# Move deal to stage (kanban drag-drop)
@router.post("/{deal_id}/move", response_model=DealResponse)
async def move_deal(
    deal_id: UUID,
    stage_id: UUID,
    current_user: tuple = Depends(require_deals_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Move a deal to a different stage."""
    from datetime import datetime, timezone
    user, membership = current_user
    
    query = select(Deal).where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
    
    if membership.role.value == "sales_executive":
        query = query.where(Deal.owner_id == user.id)
    
    result = await db.execute(query)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    
    # Verify stage
    result = await db.execute(
        select(Stage).where(Stage.id == stage_id, Stage.pipeline_id == deal.pipeline_id)
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found in this pipeline")
    
    old_stage_id = deal.stage_id
    deal.stage_id = stage_id
    deal.probability = stage.probability
    deal.weighted_value = int(deal.value * stage.probability / 100)
    deal.updated_by_id = user.id
    
    # If moved to closed won/lost, set actual close date
    if stage.is_closed and not deal.actual_close_date:
        deal.actual_close_date = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(deal)
    return scalar_response(DealResponse, deal)
