"""PostgreSQL RLS context helpers.

Request and worker isolation is transaction-local. The authoritative request
binding is app.core.tenant_context.tenant_context(), whose Session.after_begin
hook applies the verified ContextVars to the exact connection used by the
AsyncSession transaction.
"""
import contextvars
from contextlib import asynccontextmanager
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import event
from sqlalchemy.engine import Engine

current_tenant: contextvars.ContextVar[Optional[UUID]] = contextvars.ContextVar(
    "current_tenant", default=None
)
current_user_id: contextvars.ContextVar[Optional[UUID]] = contextvars.ContextVar(
    "current_user_id", default=None
)
is_admin_context: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "is_admin_context", default=False
)


async def set_rls_context(
    session: AsyncSession,
    tenant_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    is_admin: bool = False,
) -> None:
    """Set RLS variables on the supplied session's current transaction.

    ``is_local=true`` is intentional: tenant identity must never survive a
    transaction and become visible to a later request using a pooled
    connection. API requests should normally use tenant_context() instead.
    """
    current_tenant.set(tenant_id)
    current_user_id.set(user_id)
    is_admin_context.set(bool(is_admin))

    await session.execute(
        text(
            "SELECT set_config('app.current_tenant_id', :tenant, true), "
            "set_config('app.current_user_id', :actor, true), "
            "set_config('app.is_admin', :admin, true)"
        ),
        {
            "tenant": str(tenant_id or ""),
            "actor": str(user_id or ""),
            "admin": "true" if is_admin else "false",
        },
    )


async def clear_rls_context(session: AsyncSession) -> None:
    """Clear application and PostgreSQL RLS context in the current transaction."""
    current_tenant.set(None)
    current_user_id.set(None)
    is_admin_context.set(False)
    await session.execute(
        text(
            "SELECT set_config('app.current_tenant_id', '', true), "
            "set_config('app.current_user_id', '', true), "
            "set_config('app.is_admin', 'false', true)"
        )
    )


def get_current_tenant() -> Optional[UUID]:
    return current_tenant.get()


def get_current_user_id() -> Optional[UUID]:
    return current_user_id.get()


def is_admin() -> bool:
    return is_admin_context.get()


def setup_rls_event_listeners(sync_engine: Engine) -> None:
    """Compatibility hook; request RLS is bound by tenant_context.after_begin.

    Do not install a before_cursor_execute hook that mutates pooled connection
    state. SQLAlchemy's Session.after_begin hook is transaction-scoped and is
    also the supported mechanism for AsyncSession via its synchronous proxy.
    """
    return None


@asynccontextmanager
async def rls_session_context(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: Optional[UUID] = None,
    is_admin: bool = False,
):
    """Bind RLS context for an explicit transaction scope."""
    await set_rls_context(session, tenant_id, user_id, is_admin)
    try:
        yield session
    finally:
        # Keep this transaction-local; never write tenant state persistently
        # onto a pooled connection.
        await clear_rls_context(session)
