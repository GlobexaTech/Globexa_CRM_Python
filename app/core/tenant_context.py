"""Verified request/worker context, reapplied at every SQLAlchemy transaction."""
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.orm import Session

current_tenant = ContextVar("current_tenant", default=None)
current_user = ContextVar("current_user", default=None)


@contextmanager
def tenant_context(tenant_id, user_id=None):
    tenant_token = current_tenant.set(UUID(str(tenant_id)))
    user_token = current_user.set(UUID(str(user_id)) if user_id else None)
    try:
        yield
    finally:
        current_user.reset(user_token)
        current_tenant.reset(tenant_token)


@event.listens_for(Session, "after_begin")
def configure_transaction(session, transaction, connection):
    """SET LOCAL also covers transactions opened after an explicit route commit."""
    if connection.dialect.name != "postgresql":
        raise RuntimeError("PostgreSQL is required for tenant isolation")
    context = session.info.get("security_context", (current_tenant.get(), current_user.get()))
    connection.execute(text(
        "SELECT set_config('app.current_tenant_id', :tenant, true), "
        "set_config('app.current_user_id', :actor, true)"
    ), {"tenant": str(context[0] or ""), "actor": str(context[1] or "")})


async def bind_context(db, tenant_id=None, user_id=None):
    """Bind a verified identity; used during login, registration and tenant switching."""
    context = (UUID(str(tenant_id)) if tenant_id else None,
               UUID(str(user_id)) if user_id else None)
    db.info["security_context"] = context
    await db.execute(text(
        "SELECT set_config('app.current_tenant_id', :tenant, true), "
        "set_config('app.current_user_id', :actor, true)"
    ), {"tenant": str(context[0] or ""), "actor": str(context[1] or "")})


@asynccontextmanager
async def tenant_db_context(tenant_id, user_id=None):
    """A worker owns its engine so forked processes/event loops never share a pool."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool
    from app.core.config import get_settings
    with tenant_context(tenant_id, user_id):
        engine = create_async_engine(get_settings().database.url, poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                try:
                    yield db
                    from app.models import AuditLog
                    db.add(AuditLog(tenant_id=UUID(str(tenant_id)), user_id=UUID(str(user_id)) if user_id else None,
                                    action="worker.completed", resource_type="worker", success=True))
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
        finally:
            await engine.dispose()
