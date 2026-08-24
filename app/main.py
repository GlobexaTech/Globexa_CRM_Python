"""
Main FastAPI application for Globexa CRM.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import structlog

from app.core.config import get_settings
from app.core.database import init_db, close_db, engine
from app.middleware.tenant import TenantMiddleware
from app.api.v1.auth import router as auth_router
from app.api.v1.tenants import router as tenants_router
from app.api.v1.users import router as users_router
from app.api.v1.health import router as health_router
from app.api.v1.contacts import router as contacts_router
from app.api.v1.companies import router as companies_router
from app.api.v1.leads import router as leads_router
from app.api.v1.deals import router as deals_router
from app.api.v1.tasks import tasks_router as tasks_router, tasks_router as notes_router, tasks_router as activities_router
from app.api.v1.campaigns import router as campaigns_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.ai import router as ai_router

# Lazy-load settings to avoid caching at import time
def _get_settings():
    return get_settings()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer() if _get_settings().logging.format == "json" else structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Globexa CRM", version=_get_settings().app.version, environment=_get_settings().app.environment)
    await init_db()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Shutting down Globexa CRM")
    await close_db()
    logger.info("Database connections closed")


app = FastAPI(
    title=_get_settings().app.name,
    version=_get_settings().app.version,
    description="Globexa CRM - Multi-tenant AI-powered Sales CRM",
    docs_url="/docs" if _get_settings().app.debug else None,
    redoc_url="/redoc" if _get_settings().app.debug else None,
    openapi_url="/openapi.json" if _get_settings().app.debug else None,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_settings().app.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tenant middleware
app.add_middleware(TenantMiddleware, default_tenant_slug="globexatech" if _get_settings().app.debug else None)


# Exception handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(
        "HTTP exception",
        path=request.url.path,
        status_code=exc.status_code,
        detail=exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "Validation error",
        path=request.url.path,
        errors=exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception",
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Include routers
app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(companies_router, prefix="/api/v1")
app.include_router(leads_router, prefix="/api/v1")
app.include_router(deals_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(notes_router, prefix="/api/v1")
app.include_router(activities_router, prefix="/api/v1")
app.include_router(campaigns_router, prefix="/api/v1")
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")

# Root endpoint
@app.get("/")
async def root():
    return {
        "name": settings.app.name,
        "version": settings.app.version,
        "status": "running",
        "docs": "/docs" if settings.app.debug else "disabled",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
        log_config=None,  # Use structlog
    )