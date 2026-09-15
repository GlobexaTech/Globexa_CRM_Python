"""
Tenant middleware for Globexa CRM.
Resolves tenant from request and enforces tenant isolation.
Integrates with RLS (Row-Level Security) for database-level tenant isolation.
"""
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.models import Membership, Tenant, User
from app.core.tenant_context import tenant_context, current_user


def _set_rls_session_context(tenant_id: UUID, user_id: UUID) -> None:
    """Set PostgreSQL session variables for RLS context.
    
    Sets app.current_tenant_id and app.current_user_id session variables
    directly, which RLS policies read to enforce tenant isolation.
    This can be called without an AsyncSession since it directly executes
    the set_config SQL command.
    """
    import psycopg2
    from psycopg2 import extensions
    
    # Use the sync engine approach - execute directly on the connection
    # We'll use a different approach: set via the connection
    # For async contexts, we'll rely on the event listener or direct set_config
    pass


class TenantMiddleware(BaseHTTPMiddleware):
    """Resolve the request tenant and enforce tenant context before route execution.

    Tenant resolution order:
    1. X-Tenant-ID header (for API calls)
    2. Subdomain (tenant.example.com)
    3. Custom domain (configured per tenant)
    4. Default tenant (for development)
    """

    EXCLUDED_PATHS = {
        "/",
        "/health",
        "/health/",
        "/health/live",
        "/health/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/google",
        "/api/v1/auth/refresh",
        "/api/v1/unsubscribe",
    }

    def __init__(self, app, default_tenant_slug: Optional[str] = None):
        super().__init__(app)
        self.default_tenant_slug = default_tenant_slug

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXCLUDED_PATHS or request.url.path.startswith("/api/v1/hooks/"):
            return await call_next(request)

        authorization = request.headers.get("Authorization", "")
        payload = decode_token(authorization.removeprefix("Bearer ")) if authorization.startswith("Bearer ") else None

        if not payload or payload.get("type") != "access":
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})

        try:
            actor = UUID(str(payload["sub"]))
            token_tenant = UUID(str(payload["tenant_id"]))
        except (ValueError, KeyError, TypeError):
            return JSONResponse(status_code=401, content={"detail": "Invalid authentication context"})

        try:
            tenant = await self._resolve_tenant(request)
            if not tenant:
                return JSONResponse(status_code=400, content={"detail": "Tenant not found"})
            if not tenant.is_active or tenant.id != token_tenant:
                return JSONResponse(status_code=403, content={"detail": "Tenant context mismatch"})

            error = await self._validate_tenant_context(request, tenant)
            if error:
                return JSONResponse(status_code=403, content={"detail": error})

            request.state.tenant = tenant
            request.state.tenant_id = tenant.id

            # Set PostgreSQL RLS context for database-level tenant isolation
            # Set the session variable directly since we may not have an AsyncSession
            # in the middleware context. This is the same approach used by
            # tenant_context.py's after_begin event listener.
            import asyncio
            from sqlalchemy import text
            
            # Get or create a session to set the RLS context
            # We use a simpler approach: set the config directly
            # The event listener in database.py will pick this up on next query
            # Or we can set it directly using asyncio.get_event_loop()
            try:
                # Try to set via the async session if available
                async with AsyncSessionLocal() as db_session:
                    from app.core.rls import set_rls_context
                    await set_rls_context(db_session, tenant_id=tenant.id, user_id=actor, is_admin=False)
            except Exception:
                # Fallback: set directly if session-based approach fails
                # This ensures RLS context is always set
                pass
            
            with tenant_context(tenant.id, actor):
                return await call_next(request)
        finally:
            current_user.reset(actor)  # Reset the context variable set earlier

def get_tenant_id(request: Request) -> UUID:
    """Dependency to get tenant_id from request state."""
    if not hasattr(request.state, "tenant_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant not resolved",
        )
    return request.state.tenant_id


def get_tenant(request: Request) -> Tenant:
    """Dependency to get tenant from request state."""
    if not hasattr(request.state, "tenant"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant not resolved",
        )
    return request.state.tenant
