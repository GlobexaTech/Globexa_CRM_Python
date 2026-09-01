"""
Tenant middleware for Globexa CRM.
Resolves tenant from request and enforces tenant isolation.
"""
from typing import Optional
from uuid import UUID
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import Tenant, Membership


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware to resolve tenant from request and attach to request state.
    
    Tenant resolution order:
    1. X-Tenant-ID header (for API calls)
    2. Subdomain (tenant.example.com)
    3. Custom domain (configured per tenant)
    4. Default tenant (for development)
    """

    # Paths that don't require tenant resolution
    EXCLUDED_PATHS = {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/google",
        "/api/v1/auth/refresh",
    }

    def __init__(self, app, default_tenant_slug: Optional[str] = None):
        super().__init__(app)
        self.default_tenant_slug = default_tenant_slug

    async def dispatch(self, request: Request, call_next):
        # Skip tenant resolution for excluded paths
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        # Skip for websocket connections (handled separately)
        if request.url.path.startswith("/ws"):
            return await call_next(request)

        tenant = await self._resolve_tenant(request)

        if not tenant:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Tenant not found. Provide X-Tenant-ID header or use valid subdomain."},
            )

        # Attach tenant to request state
        request.state.tenant = tenant
        request.state.tenant_id = tenant.id

        # Verify tenant is active
        if not tenant.is_active:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Tenant is inactive"},
            )

        response = await call_next(request)
        return response

    async def _resolve_tenant(self, request: Request) -> Optional[Tenant]:
        """Resolve tenant from request."""
        # 1. Check X-Tenant-ID header (API clients)
        tenant_id_header = request.headers.get("X-Tenant-ID")
        if tenant_id_header:
            try:
                tenant_id = UUID(tenant_id_header)
                tenant = await self._get_tenant_by_id(tenant_id)
                if tenant:
                    # Verify the authenticated user is a member of this tenant
                    # Skip for auth endpoints that don't have user yet
                    if not request.url.path.startswith("/api/v1/auth/"):
                        user_tenant_id = getattr(request.state, "user_tenant_id", None)
                        if user_tenant_id and str(user_tenant_id) != str(tenant_id):
                            return None  # User not a member of this tenant
                return tenant
            except ValueError:
                pass

        # 2. Check subdomain (tenant.app.example.com)
        host = request.headers.get("host", "")
        if host:
            # Remove port
            host = host.split(":")[0]
            parts = host.split(".")
            if len(parts) >= 3:
                subdomain = parts[0]
                if subdomain not in {"www", "app", "api", "admin"}:
                    tenant = await self._get_tenant_by_slug(subdomain)
                    if tenant:
                        return tenant

            # 3. Check custom domain
            tenant = await self._get_tenant_by_domain(host)
            if tenant:
                return tenant

        # 4. Fallback to default tenant (development only)
        if self.default_tenant_slug:
            return await self._get_tenant_by_slug(self.default_tenant_slug)

        return None

    async def _get_tenant_by_id(self, tenant_id: UUID) -> Optional[Tenant]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
            return result.scalar_one_or_none()

    async def _get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tenant).where(Tenant.slug == slug))
            return result.scalar_one_or_none()

    async def _get_tenant_by_domain(self, domain: str) -> Optional[Tenant]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tenant).where(Tenant.domain == domain))
            return result.scalar_one_or_none()


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


class TenantScopedQuery:
    """
    Helper class to automatically scope queries to current tenant.
    Usage: query = TenantScopedQuery(db, tenant_id).query(Model)
    """

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    def query(self, model):
        """Return a query scoped to the tenant."""
        from sqlalchemy import select
        # Assumes model has tenant_id column
        return select(model).where(model.tenant_id == self.tenant_id)

    async def get(self, model, id: UUID):
        """Get a single record by ID, scoped to tenant."""
        from sqlalchemy import select
        result = await self.db.execute(
            select(model).where(
                model.id == id,
                model.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_404(self, model, id: UUID, detail: str = "Not found"):
        """Get a record or raise 404."""
        obj = await self.get(model, id)
        if not obj:
            raise HTTPException(status_code=404, detail=detail)
        return obj