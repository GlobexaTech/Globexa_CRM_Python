"""Atomic approval of imported prospects using the normal CRM contracts."""

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from app.models import PendingLead, Lead, Contact, Company, Activity, RoleEnum, LeadSourceEnum
from app.schemas import ContactCreate, LeadCreate, CompanyCreate
from app.services.crm.common import authorize, owned, serial_key, now


async def review(db, tenant_id, actor_id, source, source_id, action, values, notes):
    member = await authorize(db, tenant_id, actor_id, "leads:write")
    row = await db.scalar(
        select(PendingLead)
        .where(
            PendingLead.tenant_id == tenant_id,
            PendingLead.source == source,
            PendingLead.source_id == source_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not row or (
        member.role == RoleEnum.SALES_EXECUTIVE and row.assigned_reviewer_id not in (None, actor_id)
    ):
        raise HTTPException(404, "Pending lead not found")
    if action not in {"approve", "reject", "needs_review"}:
        raise HTTPException(422, "Invalid review action")
    if row.status == "approved":
        if action != "approve":
            raise HTTPException(409, "An approved lead cannot be rejected")
        await owned(db, Lead, tenant_id, row.created_lead_id, actor_id=actor_id)
        return {
            "success": True,
            "status": "approved",
            "lead_id": row.created_lead_id,
            "message": "Lead already approved",
        }
    if action == "approve":
        await authorize(db, tenant_id, actor_id, "contacts:write")
        data = {
            "email": row.email,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "phone": row.phone,
            "title": row.title,
            "company_name": row.company_name,
            **(values or row.raw_data or {}),
        }
        email = data.get("email")
        if not isinstance(email, str) or not email.strip():
            raise HTTPException(422, "Email is required for lead creation")
        email = email.strip().lower()
        await serial_key(db, tenant_id, "lead-review:" + email)
        source_value = data.get("source", source)
        source_value = (
            source_value if source_value in {v.value for v in LeadSourceEnum} else "other"
        )
        company_id = data.get("company_id")
        if company_id:
            from uuid import UUID

            try:
                company_id = UUID(str(company_id))
            except ValueError:
                raise HTTPException(422, "Invalid company") from None
            await owned(db, Company, tenant_id, company_id, actor_id=actor_id)
        try:
            contact_values = ContactCreate.model_validate(
                {
                    "first_name": data.get("first_name") or "Unknown",
                    "last_name": data.get("last_name") or "Contact",
                    "email": email,
                    "phone": data.get("phone"),
                    "title": data.get("title"),
                    "company_id": company_id,
                    "source": source_value,
                }
            ).model_dump()
            lead_values = LeadCreate.model_validate(
                {
                    **{
                        key: data[key]
                        for key in (
                            "description",
                            "custom_fields",
                            "utm_source",
                            "utm_medium",
                            "utm_campaign",
                            "utm_content",
                            "utm_term",
                            "referrer_url",
                            "landing_page",
                        )
                        if key in data
                    },
                    "title": data.get("title") or f"Inbound from {source}",
                    "source": source_value,
                    "source_id": source_id,
                    "company_id": company_id,
                }
            ).model_dump()
            company_name = (
                CompanyCreate(name=data["company_name"]).name if data.get("company_name") else None
            )
        except (ValidationError, TypeError):
            raise HTTPException(422, "Invalid imported contact or lead fields") from None
        if company_name and not company_id:
            await authorize(db, tenant_id, actor_id, "companies:write")
            company = await db.scalar(
                select(Company)
                .where(Company.tenant_id == tenant_id, Company.name == company_name)
                .limit(1)
            )
            if company is None:
                company = Company(tenant_id=tenant_id, name=company_name, created_by_id=actor_id)
                db.add(company)
                await db.flush()
            company_id = company.id
        contact = await db.scalar(
            select(Contact).where(Contact.tenant_id == tenant_id, Contact.email == email).limit(1)
        )
        if contact is None:
            contact_values["company_id"] = company_id
            contact = Contact(tenant_id=tenant_id, created_by_id=actor_id, **contact_values)
            db.add(contact)
            await db.flush()
        lead = await db.scalar(
            select(Lead)
            .where(Lead.tenant_id == tenant_id, Lead.contact_id == contact.id)
            .order_by(Lead.created_at)
            .limit(1)
        )
        if lead is not None:
            await owned(db, Lead, tenant_id, lead.id, actor_id=actor_id)
        else:
            lead_values.update(contact_id=contact.id, company_id=company_id, owner_id=actor_id)
            lead = Lead(tenant_id=tenant_id, created_by_id=actor_id, **lead_values)
            db.add(lead)
            await db.flush()
            db.add(
                Activity(
                    tenant_id=tenant_id,
                    lead_id=lead.id,
                    contact_id=contact.id,
                    type="ai_action",
                    subject=f"Lead approved from {source}",
                    user_id=actor_id,
                    metadata_={"source": source, "source_id": source_id},
                )
            )
        row.created_lead_id, row.created_contact_id = lead.id, contact.id
    row.status = {"approve": "approved", "reject": "rejected", "needs_review": "needs_review"}[
        action
    ]
    row.reviewed_by_id, row.reviewed_at, row.review_notes = actor_id, now(), notes
    await db.flush()
    return {
        "success": True,
        "status": row.status,
        "lead_id": row.created_lead_id,
        "message": "Lead review saved",
    }
