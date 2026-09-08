"""
Tenant middleware for Globexa CRM.
Resolves tenant from request and enforces tenant isolation.
"""
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.models import Membership, Tenant


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Resolve the request tenant and enforce tenant context before route execution.

    Tenant resolution order:
    1. X-Tenant-ID header
    2. Subdomain
    3. Custom domain
    4. Default tenant (development only)
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
    }

    def __init__(self, app, default_tenant_slug: Optional[str] = None):
        super().__init__(app)
        self.default_tenant_slug = default_tenant_slug

    async def dispatch(self, request: Request, call_next):
        from app.core.tenant_context import tenant_context, current_user
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
        identity_token = current_user.set(actor)
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
            with tenant_context(tenant.id, actor):
                return await call_next(request)
        finally:
            current_user.reset(identity_token)

    async def _validate_tenant_context(
        self,
        request: Request,
        tenant: Tenant,
    ) -> Optional[str]:
        """Validate URL/header/JWT tenant context before protected route execution."""
        path_tenant_id = self._tenant_id_from_path(request.url.path)
        if path_tenant_id and path_tenant_id != tenant.id:
            return "Requested tenant does not match the active tenant context"

        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            # Authentication dependencies remain responsible for missing credentials.
            return None

        payload = decode_token(authorization.removeprefix("Bearer ").strip())
        if not payload or payload.get("type") != "access":
            # Authentication dependencies return the canonical 401 for bad tokens.
            return None

        token_tenant_id = payload.get("tenant_id")
        if not token_tenant_id or str(token_tenant_id) != str(tenant.id):
            return "X-Tenant-ID does not match the authenticated tenant"

        user_id = payload.get("sub")
        if not user_id:
            return None

        try:
            user_uuid = UUID(str(user_id))
        except (TypeError, ValueError):
            return None

        if not await self._has_membership(user_uuid, tenant.id):
            return "Authenticated user is not a member of this tenant"

        request.state.user_tenant_id = tenant.id
        return None

    @staticmethod
    def _tenant_id_from_path(path: str) -> Optional[UUID]:
        """
        Extract tenant UUID from /api/v1/tenants/{tenant_id}[/*] routes.

        This prevents a valid tenant context from being used to access another
        tenant through a path parameter.
        """
        prefix = "/api/v1/tenants/"
        if not path.startswith(prefix):
            return None

        candidate = path[len(prefix):].split("/", 1)[0]
        if not candidate or candidate == "me":
            return None

        try:
            return UUID(candidate)
        except ValueError:
            return None

    async def _resolve_tenant(self, request: Request) -> Optional[Tenant]:
        """Resolve tenant from header, host, or development fallback."""
        tenant_id_header = request.headers.get("X-Tenant-ID")
        if tenant_id_header:
            try:
                tenant = await self._get_tenant_by_id(UUID(tenant_id_header))
                if tenant:
                    return tenant
            except ValueError:
                pass

        host = request.headers.get("host", "")
        if host:
            host = host.split(":")[0]
            parts = host.split(".")
            if len(parts) >= 3:
                subdomain = parts[0]
                if subdomain not in {"www", "app", "api", "admin"}:
                    tenant = await self._get_tenant_by_slug(subdomain)
                    if tenant:
                        return tenant

            tenant = await self._get_tenant_by_domain(host)
            if tenant:
                return tenant

        if self.default_tenant_slug:
            return await self._get_tenant_by_slug(self.default_tenant_slug)

        return None

    async def _has_membership(self, user_id: UUID, tenant_id: UUID) -> bool:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Membership.id).where(
                    Membership.user_id == user_id,
                    Membership.tenant_id == tenant_id,
                )
            )
            return result.scalar_one_or_none() is not None

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
    """Helper to scope SQLAlchemy queries to a tenant_id column."""

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    def query(self, model):
        return select(model).where(model.tenant_id == self.tenant_id)

    async def get(self, model, id: UUID):
        result = await self.db.execute(
            select(model).where(
                model.id == id,
                model.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_404(self, model, id: UUID, detail: str = "Not found"):
        obj = await self.get(model, id)
        if not obj:
            raise HTTPException(status_code=404, detail=detail)
        return obj
