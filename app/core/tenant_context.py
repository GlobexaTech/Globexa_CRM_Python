"""Database tenant context management for PostgreSQL RLS."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_session import AsyncSessionLocal


async def set_tenant_context(session: AsyncSession, tenant_id: UUID) -> None:
    """Set the tenant context for RLS policies on the current session.
    
    Uses SET LOCAL to ensure the setting only applies to the current transaction.
    This is critical for connection pooling - the setting will not leak between
    pooled connections.
    """
    await session.execute(text("SET LOCAL app.current_tenant_id = :tenant_id"), {"tenant_id": str(tenant_id)})


async def clear_tenant_context(session: AsyncSession) -> None:
    """Clear the tenant context (optional, for cleanup)."""
    await session.execute(text("SET LOCAL app.current_tenant_id = ''"))


@asynccontextmanager
async def tenant_db_context(tenant_id: UUID) -> AsyncGenerator:
    """Context manager for database operations with tenant context.
    
    Creates a new session, sets tenant context, and yields the session.
    Automatically commits/rollbacks and closes the session.
    
    Usage:
        async with tenant_db_context(tenant_id) as session:
            result = await session.execute(...)
    """
    async with AsyncSessionLocal() as session:
        try:
            await set_tenant_context(session, tenant_id)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_tenant_db(tenant_id: UUID):
    """FastAPI dependency for database session with tenant context.
    
    Usage:
        @router.get("/leads")
        async def get_leads(db: AsyncSession = Depends(get_tenant_db(tenant_id))):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            await set_tenant_context(session, tenant_id)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class TenantSessionMixin:
    """Mixin to add tenant context support to a session or repository."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def set_tenant(self, tenant_id: UUID) -> None:
        """Set tenant context on the session."""
        await set_tenant_context(self.session, tenant_id)
    
    async def clear_tenant(self) -> None:
        """Clear tenant context."""
        await clear_tenant_context(self.session)