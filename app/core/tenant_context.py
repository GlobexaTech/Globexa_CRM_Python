"""
Tenant Database Context Management

Provides safe transaction-local PostgreSQL tenant context using SET LOCAL
app.current_tenant_id for RLS enforcement.
"""

from contextlib import asynccontextmanager
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal


class TenantContext:
    """Manages tenant context for database sessions."""
    
    @staticmethod
    async def set_tenant_id(session: AsyncSession, tenant_id: UUID) -> None:
        """Set the tenant context for the current transaction using SET LOCAL."""
        await session.execute(
            text("SELECT set_tenant_context(:tenant_id)"),
            {"tenant_id": str(tenant_id)}
        )
    
    @staticmethod
    async def get_tenant_id(session: AsyncSession) -> Optional[UUID]:
        """Get the current tenant context."""
        result = await session.execute(text("SELECT get_tenant_context()"))
        tenant_id_str = result.scalar()
        if tenant_id_str:
            return UUID(tenant_id_str)
        return None
    
    @staticmethod
    async def clear_tenant_id(session: AsyncSession) -> None:
        """Clear the tenant context (set to empty string)."""
        await session.execute(text("SELECT set_config('app.current_tenant_id', '', true)"))


@asynccontextmanager
async def tenant_db_context(tenant_id: UUID) -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager that provides a database session with tenant context established.
    
    This ensures RLS policies are enforced for all queries within the context.
    The tenant context is set using SET LOCAL which is transaction-scoped and
    does not leak between pooled connections.
    
    Usage:
        async with tenant_db_context(tenant_id) as db:
            # All queries here are tenant-isolated by RLS
            result = await db.execute(select(Contact))
    """
    async with AsyncSessionLocal() as session:
        try:
            # Establish tenant context before any tenant-scoped queries
            await TenantContext.set_tenant_id(session, tenant_id)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def tenant_db_context_optional(tenant_id: Optional[UUID] = None) -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager with optional tenant context.
    
    If tenant_id is provided, establishes tenant context.
    If None, session operates without tenant context (e.g., for superuser operations).
    """
    async with AsyncSessionLocal() as session:
        try:
            if tenant_id is not None:
                await TenantContext.set_tenant_id(session, tenant_id)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def verify_tenant_access(
    session: AsyncSession,
    user_id: UUID,
    tenant_id: UUID
) -> bool:
    """
    Verify that a user is an active member of a tenant.
    
    This is the bootstrap verification that must happen BEFORE
    establishing RLS tenant context, since membership table itself
    is protected by RLS.
    """
    # Use a separate session without RLS context for membership lookup
    # or use the SECURITY DEFINER function approach
    from sqlalchemy import select
    from app.models import Membership, RoleEnum
    
    result = await session.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
        )
    )
    membership = result.scalar_one_or_none()
    
    if membership and membership.user.is_active:
        return True
    return False