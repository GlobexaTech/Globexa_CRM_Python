"""Small, permission-checked CRM snapshots for conditions, templates and AI."""

from uuid import UUID
from fastapi.encoders import jsonable_encoder
from app.models import Lead, Contact, Deal, Task, Message, Campaign, Company, User
from app.services.crm.common import owned, authorize
from app.services.automation.expressions import FIELDS

MODELS = {
    "lead": Lead,
    "contact": Contact,
    "deal": Deal,
    "task": Task,
    "message": Message,
    "campaign": Campaign,
}
PERMISSIONS = {key: key + "s:read" for key in MODELS}
PERMISSIONS["message"] = "conversations:read"


async def snapshot(db, tenant_id, actor_id, entity):
    result = {}
    if entity and entity.get("entity_type"):
        kind, identifier = entity["entity_type"], UUID(str(entity["entity_id"]))
        await authorize(db, tenant_id, actor_id, PERMISSIONS[kind])
        row = await owned(db, MODELS[kind], tenant_id, identifier)
        await db.refresh(row)
        result[kind] = jsonable_encoder(
            {field: getattr(row, field) for field in FIELDS[kind] if hasattr(row, field)}
        )
        if kind == "lead":
            result[kind].update(score=row.ai_score, stage=getattr(row.status, "value", row.status))
            if row.contact_id:
                await authorize(db, tenant_id, actor_id, "contacts:read")
                contact = await owned(db, Contact, tenant_id, row.contact_id)
                result[kind].update(first_name=contact.first_name, email=contact.email)
        if kind == "contact" and row.company_id:
            await authorize(db, tenant_id, actor_id, "companies:read")
            company = await owned(db, Company, tenant_id, row.company_id)
            result[kind]["company"] = company.name
    user = await db.get(User, actor_id)
    result["current_user"] = {"id": str(actor_id), "name": user.full_name if user else ""}
    return result
