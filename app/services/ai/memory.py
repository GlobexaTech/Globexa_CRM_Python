"""Tenant-isolated working memory and explicitly approved expiring long-term memory."""

from datetime import timedelta
from sqlalchemy import select, delete
from app.models import AgentMemory
from app.services.crm.common import authorize, audit, now, serial_key
from app.services.ai.safety import safe_data


async def purge_expired(db, tenant_id):
    await db.execute(
        delete(AgentMemory).where(
            AgentMemory.tenant_id == tenant_id, AgentMemory.expires_at <= now()
        )
    )


async def store_working(db, execution, value):
    # Persist only execution metadata, never raw messages, web pages or full customer records.
    key = "execution:" + str(execution.id)
    await serial_key(db, execution.tenant_id, "memory:" + key)
    row = await db.scalar(
        select(AgentMemory).where(
            AgentMemory.tenant_id == execution.tenant_id,
            AgentMemory.agent_name == execution.agent_name,
            AgentMemory.memory_type == "working",
            AgentMemory.key == key,
        )
    )
    if not row:
        row = AgentMemory(
            tenant_id=execution.tenant_id,
            actor_id=execution.actor_id,
            execution_id=execution.id,
            agent_name=execution.agent_name,
            memory_type="working",
            key=key,
        )
        db.add(row)
    row.value = {
        "execution_id": str(execution.id),
        "state": value["state"],
        "tool_names": value.get("tool_names", []),
    }
    row.expires_at = now() + timedelta(hours=24)
    await db.flush()


async def store_approved(db, tenant_id, actor_id, approver_id, arguments):
    from app.schemas.workforce import MemoryInput

    data = MemoryInput.model_validate(arguments)
    safe_data(data.value)
    await authorize(db, tenant_id, actor_id, "ai:chat")
    await authorize(db, tenant_id, approver_id, "ai:approve")
    await serial_key(db, tenant_id, "memory:" + data.agent_name + ":" + data.key)
    row = await db.scalar(
        select(AgentMemory)
        .where(
            AgentMemory.tenant_id == tenant_id,
            AgentMemory.agent_name == data.agent_name,
            AgentMemory.memory_type == "long_term",
            AgentMemory.key == data.key,
        )
        .with_for_update()
    )
    if not row:
        row = AgentMemory(
            tenant_id=tenant_id,
            actor_id=actor_id,
            agent_name=data.agent_name,
            memory_type="long_term",
            key=data.key,
        )
        db.add(row)
    row.actor_id, row.approved_by, row.value = actor_id, approver_id, data.value
    row.expires_at = now() + timedelta(days=data.retention_days)
    await db.flush()
    audit(db, tenant_id, approver_id, "memory.approved", "agent_memory", row.id)
    return {"memory_id": str(row.id), "expires_at": row.expires_at.isoformat()}


async def recall(db, tenant_id, actor_id, agent_name):
    await authorize(db, tenant_id, actor_id, "ai:chat")
    await purge_expired(db, tenant_id)
    rows = (
        await db.scalars(
            select(AgentMemory)
            .where(
                AgentMemory.tenant_id == tenant_id,
                AgentMemory.actor_id == actor_id,
                AgentMemory.agent_name == agent_name,
                AgentMemory.memory_type == "long_term",
                AgentMemory.approved_by.is_not(None),
                AgentMemory.expires_at > now(),
            )
            .limit(10)
        )
    ).all()
    return [{"key": row.key, "value": row.value, "untrusted": True} for row in rows]
