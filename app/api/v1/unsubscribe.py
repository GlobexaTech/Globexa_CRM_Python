from uuid import UUID
from html import escape
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.security import decode_token
from app.core.tenant_context import bind_context
from app.models import Contact, SuppressionList
from app.services.crm.common import owned, audit

router = APIRouter(prefix="/unsubscribe", tags=["Email preferences"])


def validate(token):
    payload = decode_token(token)
    if not payload or payload.get("type") != "unsubscribe":
        raise HTTPException(400, "Unsubscribe link is invalid or expired")
    try:
        return UUID(payload["tenant_id"]), UUID(payload["sub"])
    except (ValueError, KeyError):
        raise HTTPException(400, "Unsubscribe link is invalid") from None


@router.get("", response_class=HTMLResponse)
async def confirm(token: str = Query(min_length=20, max_length=2000)):
    validate(token)
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Email preferences</title><h1>Unsubscribe</h1><form method="post" action="?token='
        + escape(token, quote=True)
        + '"><button type="submit">Stop campaign emails</button></form></html>'
    )


@router.post("", response_model=dict)
async def unsubscribe(
    token: str = Query(min_length=20, max_length=2000), db=Depends(get_db)
):
    tenant_id, contact_id = validate(token)
    await bind_context(db, tenant_id)
    contact = await owned(db, Contact, tenant_id, contact_id, True)
    contact.email_opted_out = True
    if contact.email:
        existing = await db.scalar(
            select(SuppressionList)
            .where(
                SuppressionList.tenant_id == tenant_id,
                func.lower(SuppressionList.email) == contact.email.lower(),
            )
            .limit(1)
        )
        if not existing:
            db.add(
                SuppressionList(
                    tenant_id=tenant_id,
                    contact_id=contact.id,
                    email=contact.email.lower(),
                    reason="unsubscribe",
                )
            )
        else:
            existing.is_active = True
    audit(db, tenant_id, None, "contact.unsubscribed", "contact", contact_id)
    await db.commit()
    return {"status": "unsubscribed"}
