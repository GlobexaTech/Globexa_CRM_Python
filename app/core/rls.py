"""
Database context management for RLS (Row-Level Security).
Sets the current tenant ID per request/session so PostgreSQL policies apply automatically.
"""
import contextvars
from typing import Optional
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import event
from sqlalchemy.engine import Engine

# Context variable to store current tenant per request
current_tenant: contextvars.ContextVar[Optional[UUID]] = contextvars.ContextVar("current_tenant", default=None)
current_user_id: contextvars.ContextVar[Optional[UUID]] = contextvars.ContextVar("current_user_id", default=None)
is_admin_context: contextvars.ContextVar[bool] = contextvars.ContextVar("is_admin_context", default=False)


async def set_rls_context(
    session: AsyncSession,
    tenant_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    is_admin: bool = False,
) -> None:
    """
    Set the RLS context for the current database session.
    This sets PostgreSQL session variables that RLS policies read.
    
    Args:
        session: Async database session
        tenant_id: Current tenant UUID (required for tenant isolation)
        user_id: Current user UUID (for audit/user-level policies)
        is_admin: Whether this is an admin context (bypasses RLS if using BYPASSRLS role)
    """
    # Set context variables
    if tenant_id is not None:
        current_tenant.set(tenant_id)
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, false)"),
            {"tid": str(tenant_id)}
        )
    
    if user_id is not None:
        current_user_id.set(user_id)
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, false)"),
            {"uid": str(user_id)}
        )
    
    if is_admin:
        is_admin_context.set(True)
        await session.execute(
            text("SELECT set_config('app.is_admin', 'true', false)")
        )
    else:
        is_admin_context.set(False)
        await session.execute(
            text("SELECT set_config('app.is_admin', 'false', false)")
        )


async def clear_rls_context(session: AsyncSession) -> None:
    """Clear RLS context variables."""
    current_tenant.set(None)
    current_user_id.set(None)
    is_admin_context.set(False)
    
    await session.execute(text("SELECT set_config('app.current_tenant_id', '', false)"))
    await session.execute(text("SELECT set_config('app.current_user_id', '', false)"))
    await session.execute(text("SELECT set_config('app.is_admin', 'false', false)"))


def get_current_tenant() -> Optional[UUID]:
    """Get current tenant from context variable."""
    return current_tenant.get()


def get_current_user_id() -> Optional[UUID]:
    """Get current user ID from context variable."""
    return current_user_id.get()


def is_admin() -> bool:
    """Check if current context is admin."""
    return is_admin_context.get()


# SQLAlchemy event listener for automatic tenant setting
# This can be used as an alternative to manual set_rls_context calls
def setup_rls_event_listeners(sync_engine: Engine) -> None:
    """
    Set up SQLAlchemy event listeners to automatically set tenant context.
    This runs before each cursor execute, setting the tenant from context variable.
    
    Args:
        sync_engine: The synchronous SQLAlchemy engine (from create_engine, not create_async_engine)
    """
    
    @event.listens_for(sync_engine, "before_cursor_execute")
    def set_tenant_on_execute(conn, cursor, statement, parameters, context, executemany):
        """Set tenant context before each SQL execution."""
        tid = current_tenant.get()
        if tid is not None:
            # Use SET LOCAL for transaction-scoped setting
            cursor.execute(f"SET LOCAL app.current_tenant_id = '{tid}'")
        
        uid = current_user_id.get()
        if uid is not None:
            cursor.execute(f"SET LOCAL app.current_user_id = '{uid}'")
        
        admin = is_admin_context.get()
        if admin:
            cursor.execute("SET LOCAL app.is_admin = 'true'")
        else:
            cursor.execute("SET LOCAL app.is_admin = 'false'")


# Alternative: Session-scoped context manager
from contextlib import asynccontextmanager

@asynccontextmanager
async def rls_session_context(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: Optional[UUID] = None,
    is_admin: bool = False,
):
    """
    Context manager for RLS session.
    Automatically sets and clears RLS context.
    
    Usage:
        async with rls_session_context(db, tenant_id, user_id) as session:
            # All queries in this block are tenant-scoped
            users = await session.execute(select(User))
    """
    await set_rls_context(session, tenant_id, user_id, is_admin)
    try:
        yield session
    finally:
        await clear_rls_context(session)