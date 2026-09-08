from datetime import datetime, timezone
import hashlib
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models import Membership, User, AuditLog, OperationJob
from app.core.rbac import get_role_permissions
from app.core.entitlements import EntitlementService, EntitlementDenied


def now():
    return datetime.now(timezone.utc)


async def owned(db, model, tenant_id, entity_id, lock=False):
    stmt = select(model).where(model.tenant_id == tenant_id, model.id == entity_id)
    row = await db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise HTTPException(404, "Resource not found")
    return row


async def authorize(db, tenant_id, actor_id, permission):
    member = await db.scalar(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == actor_id,
            User.is_active.is_(True),
        )
    )
    if member is None or permission not in get_role_permissions(member.role):
        raise HTTPException(403, "Permission required: " + permission)
    return member


async def meter(db, tenant_id, actor_id, feature, quantity=1):
    try:
        await EntitlementService(db).consume(tenant_id, feature, quantity, actor_id)
    except EntitlementDenied as exc:
        raise HTTPException(403, str(exc)) from None


def audit(db, tenant_id, actor_id, action, entity, entity_id, success=True):
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=actor_id,
            action=action,
            resource_type=entity,
            resource_id=str(entity_id),
            success=success,
        )
    )


async def serial_key(db, tenant_id, key):
    # Scoped advisory locks serialize insertion before a unique row exists.
    digest = hashlib.sha256(f"{tenant_id}:{key}".encode()).digest()
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(digest[:8], "big", signed=True)},
    )


async def enqueue(
    db, tenant_id, actor_id, kind, key, payload, *, available_at=None, status="pending"
):
    await serial_key(db, tenant_id, key)
    existing = await db.scalar(
        select(OperationJob).where(
            OperationJob.tenant_id == tenant_id, OperationJob.idempotency_key == key
        )
    )
    if existing:
        if (
            existing.kind != kind
            or existing.payload != payload
            or existing.actor_id != actor_id
        ):
            raise HTTPException(409, "Idempotency key was used with different input")
        return existing, False
    row = OperationJob(
        tenant_id=tenant_id,
        actor_id=actor_id,
        kind=kind,
        idempotency_key=key,
        payload=payload,
        status=status,
        available_at=available_at or now(),
    )
    db.add(row)
    await db.flush()
    return row, True


def public_job(job):
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "attempts": job.attempts,
        "result": job.result,
        "error_code": job.error_code,
        "created_at": job.created_at,
    }
