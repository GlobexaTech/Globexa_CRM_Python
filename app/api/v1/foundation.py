"""Permission-checked APIs for architectural foundations; no autonomous runner."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_tenant_id, get_current_active_user, require_admin, get_role_permissions
from app.core.database import get_db
from app.core.search import PostgresSearch
from app.models import Workflow, Trigger, Condition, Action, FeatureEntitlement, AuditLog, OAuthToken, Integration

router = APIRouter(prefix="/foundation", tags=["Architecture foundation"])


class WorkflowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    trigger: str
    condition: dict = Field(default_factory=dict)
    tool: str
    arguments: dict = Field(default_factory=dict)


@router.post("/workflows", status_code=201)
async def create_workflow(data: WorkflowInput, identity=Depends(require_admin),
                          tenant_id: UUID = Depends(get_tenant_id), db: AsyncSession = Depends(get_db)):
    from app.core.events import EVENT_TYPES
    from app.services.ai.tools import APPROVED_TOOLS
    if data.trigger not in EVENT_TYPES or data.tool not in APPROVED_TOOLS:
        raise HTTPException(422, "Unapproved trigger or tool")
    if set(data.condition) - {"field", "operator", "value"} or data.condition.get("operator", "eq") not in {"eq", "ne"}:
        raise HTTPException(422, "Unsupported condition")
    workflow = Workflow(tenant_id=tenant_id, name=data.name, enabled=False)
    db.add(workflow)
    await db.flush()
    db.add_all([Trigger(tenant_id=tenant_id, workflow_id=workflow.id, event_type=data.trigger),
                Condition(tenant_id=tenant_id, workflow_id=workflow.id, expression=data.condition),
                Action(tenant_id=tenant_id, workflow_id=workflow.id, tool=data.tool, arguments=data.arguments)])
    await db.flush()
    return {"id": str(workflow.id), "enabled": False, "version": workflow.version}


@router.get("/workflows")
async def list_workflows(identity=Depends(require_admin), tenant_id: UUID = Depends(get_tenant_id),
                         db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Workflow).where(Workflow.tenant_id == tenant_id).limit(100))).all()
    return [{"id": str(row.id), "name": row.name, "enabled": row.enabled} for row in rows]


@router.get("/search")
async def search(entity: str, q: str, identity=Depends(get_current_active_user),
                  tenant_id: UUID = Depends(get_tenant_id), db: AsyncSession = Depends(get_db)):
    permission = {"leads": "leads:read", "contacts": "contacts:read", "messages": "ai:chat",
                  "tasks": "tasks:read", "campaigns": "campaigns:read", "agents": "ai:chat"}.get(entity)
    if permission not in get_role_permissions(identity[1].role):
        raise HTTPException(403, "Search permission required")
    try:
        return await PostgresSearch(db).search(tenant_id, entity, q)
    except ValueError:
        raise HTTPException(422, "Invalid search") from None


@router.get("/entitlements")
async def entitlements(identity=Depends(get_current_active_user), tenant_id: UUID = Depends(get_tenant_id),
                        db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(FeatureEntitlement).where(FeatureEntitlement.tenant_id == tenant_id))).all()
    return [{"feature": row.feature_key, "enabled": row.enabled, "limit": row.limit_value} for row in rows]


@router.get("/audit")
async def audit(identity=Depends(require_admin), tenant_id: UUID = Depends(get_tenant_id),
                 db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(AuditLog).where(AuditLog.tenant_id == tenant_id)
                             .order_by(AuditLog.created_at.desc()).limit(100))).all()
    return [{"action": row.action, "resource_type": row.resource_type, "resource_id": row.resource_id,
              "success": row.success, "created_at": row.created_at} for row in rows]


class OAuthInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    integration_id: UUID
    access_token: str = Field(min_length=1)
    refresh_token: str | None = None
    scopes: list[str] = Field(default_factory=list)


@router.post("/oauth-tokens", status_code=201)
async def oauth_token(data: OAuthInput, identity=Depends(require_admin),
                       tenant_id: UUID = Depends(get_tenant_id), db: AsyncSession = Depends(get_db)):
    parent = await db.scalar(select(Integration).where(Integration.id == data.integration_id,
                                                       Integration.tenant_id == tenant_id))
    if parent is None:
        raise HTTPException(404, "Integration not found")
    item = OAuthToken(tenant_id=tenant_id, **data.model_dump())
    db.add(item)
    await db.flush()
    return {"id": str(item.id), "integration_id": str(parent.id), "scopes": item.scopes}
