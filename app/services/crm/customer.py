"""Customer overview and timeline built from tenant-scoped, permission-filtered resources."""

from uuid import UUID
from sqlalchemy import select, or_
from app.models import (
    Company,
    Contact,
    Lead,
    Deal,
    Task,
    Note,
    Activity,
    Conversation,
    Message,
    CampaignRecipient,
    Campaign,
    DomainEvent,
    AIInsight,
)
from app.core.rbac import get_role_permissions
from app.services.crm.common import owned, authorize

MODELS = {"contacts": Contact, "companies": Company, "leads": Lead}
PERMISSIONS = {
    "companies": "companies:read",
    "contacts": "contacts:read",
    "leads": "leads:read",
    "deals": "deals:read",
    "tasks": "tasks:read",
    "notes": "notes:read",
    "activities": "tasks:read",
    "conversations": "conversations:read",
    "messages": "conversations:read",
    "campaigns": "campaigns:read",
    "integrations": "integrations:read",
    "ai_insights": "ai:chat",
}


def summary(row):
    fields = {
        "id",
        "name",
        "first_name",
        "last_name",
        "email",
        "title",
        "subject",
        "content",
        "body",
        "description",
        "status",
        "value",
        "stage_id",
        "due_date",
        "completed_at",
        "created_at",
        "occurred_at",
        "channel",
        "sender",
        "recipient",
        "provider_message_id",
        "capability",
        "output",
        "last_message_at",
        "unread_count",
    }
    return {key: getattr(row, key) for key in fields if hasattr(row, key)}


async def customer360(db, tenant_id, actor_id, kind, entity_id, limit=50, offset=0):
    if kind not in MODELS:
        from fastapi import HTTPException

        raise HTTPException(422, "Customer type must be contacts, companies or leads")
    member = await authorize(db, tenant_id, actor_id, PERMISSIONS[kind])
    allowed = get_role_permissions(member.role)
    root = await owned(db, MODELS[kind], tenant_id, entity_id)
    company_id = root.id if kind == "companies" else root.company_id
    contact_ids = (
        [root.id]
        if kind == "contacts"
        else ([root.contact_id] if kind == "leads" and root.contact_id else [])
    )
    if kind == "companies":
        contact_ids = list(
            (
                await db.scalars(
                    select(Contact.id).where(
                        Contact.tenant_id == tenant_id, Contact.company_id == root.id
                    )
                )
            ).all()
        )
    lead_ids = list(
        (
            await db.scalars(
                select(Lead.id).where(
                    Lead.tenant_id == tenant_id,
                    or_(
                        Lead.id == root.id if kind == "leads" else False,
                        Lead.contact_id.in_(contact_ids),
                        Lead.company_id == root.id if kind == "companies" else False,
                    ),
                )
            )
        ).all()
    )
    deal_ids = list(
        (
            await db.scalars(
                select(Deal.id).where(
                    Deal.tenant_id == tenant_id,
                    or_(
                        Deal.contact_id.in_(contact_ids),
                        Deal.lead_id.in_(lead_ids),
                        Deal.company_id == root.id if kind == "companies" else False,
                    ),
                )
            )
        ).all()
    )
    result = {"customer": summary(root), "restricted_sections": [], "sections": {}}
    entities = {str(root.id)}
    event_prefixes = set()
    mapping = {
        "companies": (Company, Company.id == company_id),
        "contacts": (Contact, Contact.id.in_(contact_ids)),
        "leads": (Lead, Lead.id.in_(lead_ids)),
        "deals": (Deal, Deal.id.in_(deal_ids)),
    }
    for name, model in {
        "tasks": Task,
        "notes": Note,
        "activities": Activity,
        "conversations": Conversation,
    }.items():
        conditions = [
            model.contact_id.in_(contact_ids),
            model.lead_id.in_(lead_ids),
            model.company_id == root.id if kind == "companies" else False,
        ]
        if hasattr(model, "deal_id"):
            conditions.append(model.deal_id.in_(deal_ids))
        mapping[name] = (model, or_(*conditions))
    conv_ids = []
    for name, (model, clause) in mapping.items():
        if PERMISSIONS[name] not in allowed:
            result["restricted_sections"].append(name)
            continue
        rows = (
            await db.scalars(
                select(model)
                .where(model.tenant_id == tenant_id, clause)
                .order_by(model.created_at.desc())
                .limit(200)
            )
        ).all()
        result["sections"][name] = [summary(row) for row in rows]
        entities.update(str(row.id) for row in rows)
        event_prefixes.add(
            {
                "companies": "company",
                "contacts": "contact",
                "leads": "lead",
                "deals": "deal",
                "tasks": "task",
                "notes": "note",
                "activities": "activity",
                "conversations": "conversation",
            }[name]
        )
        if model is Conversation:
            conv_ids = [row.id for row in rows]
    if "conversations:read" in allowed:
        messages = (
            await db.scalars(
                select(Message)
                .where(
                    Message.tenant_id == tenant_id,
                    Message.conversation_id.in_(conv_ids),
                )
                .order_by(Message.occurred_at.desc())
                .limit(200)
            )
        ).all()
        result["sections"]["messages"] = [summary(row) for row in messages]
        entities.update(str(row.id) for row in messages)
        event_prefixes.add("message")
    if "campaigns:read" in allowed:
        recipients = (
            await db.scalars(
                select(CampaignRecipient)
                .where(
                    CampaignRecipient.tenant_id == tenant_id,
                    CampaignRecipient.contact_id.in_(contact_ids),
                )
                .order_by(CampaignRecipient.created_at.desc())
                .limit(200)
            )
        ).all()
        campaigns = (
            await db.scalars(
                select(Campaign).where(
                    Campaign.tenant_id == tenant_id,
                    Campaign.id.in_([r.campaign_id for r in recipients]),
                )
            )
        ).all()
        result["sections"]["campaigns"] = [summary(row) for row in campaigns]
        result["sections"]["email_history"] = [
            {
                "id": r.id,
                "campaign_id": r.campaign_id,
                "status": r.status.value,
                "sent_at": r.sent_at,
                "replied_at": r.replied_at,
                "provider_message_id": r.provider_message_id,
            }
            for r in recipients
        ]
    if "ai:chat" in allowed:
        insights = (
            await db.scalars(
                select(AIInsight)
                .where(
                    AIInsight.tenant_id == tenant_id,
                    AIInsight.entity_id.in_([UUID(v) for v in entities]),
                )
                .order_by(AIInsight.created_at.desc())
                .limit(50)
            )
        ).all()
        result["sections"]["ai_insights"] = [summary(row) for row in insights]
        event_prefixes.add("ai")
    # Integration history includes only messages linked to this customer's conversations.
    if "integrations:read" in allowed and "conversations:read" in allowed:
        result["sections"]["integration_activity"] = [
            {"conversation_id": r["id"], "last_message_at": r.get("last_message_at")}
            for r in result["sections"].get("conversations", [])
        ]
    query = select(DomainEvent).where(
        DomainEvent.tenant_id == tenant_id,
        DomainEvent.aggregate_id.in_(entities),
        or_(*(DomainEvent.event_type.like(prefix + ".%") for prefix in event_prefixes)),
    )
    timeline = (
        await db.scalars(
            query.order_by(DomainEvent.created_at.desc(), DomainEvent.id)
            .offset(offset)
            .limit(limit + 1)
        )
    ).all()
    result["timeline"] = [
        {
            "id": e.id,
            "type": e.event_type,
            "entity_id": e.aggregate_id,
            "occurred_at": e.created_at,
            "version": e.version,
        }
        for e in timeline[:limit]
    ]
    result["pagination"] = {
        "limit": limit,
        "offset": offset,
        "has_more": len(timeline) > limit,
        "section_limit": 200,
    }
    return result
