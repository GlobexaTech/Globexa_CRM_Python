"""
Main FastAPI application for Globexa CRM.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from app.core.input_security import protect_input
from app.api.v1.hooks import router as hooks_router
from app.api.v1.foundation import router as foundation_router
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
from app.api.v1.leads import leads_router, firecrawl_router
from app.api.v1.deals import router as deals_router
from app.api.v1.tasks import tasks_router
from app.api.v1.tasks import notes_router
from app.api.v1.tasks import activities_router
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


from app.core.rate_limit import enforce_rate

app = FastAPI(
    title=_get_settings().app.name,
    version=_get_settings().app.version,
    description="Globexa CRM - Multi-tenant AI-powered Sales CRM",
    docs_url="/docs" if _get_settings().app.debug else None,
    redoc_url="/redoc" if _get_settings().app.debug else None,
    openapi_url="/openapi.json" if _get_settings().app.debug else None,
    lifespan=lifespan,
    dependencies=[Depends(protect_input), Depends(enforce_rate)],
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
from fastapi.exceptions import ResponseValidationError


@app.exception_handler(ResponseValidationError)
async def response_validation_exception_handler(request: Request, exc: ResponseValidationError):
    # ResponseValidationError.__str__ can contain complete ORM inputs. Handle
    # it explicitly so Uvicorn does not print payloads after the safe response.
    logger.error("Response validation failed", path=request.url.path,
                 errors=[{"loc": e["loc"], "type": e["type"]} for e in exc.errors()])
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


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
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "Validation error",
        path=request.url.path,
        errors=[{"loc": e["loc"], "type": e["type"]} for e in exc.errors()],
    )
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "errors": [{"loc": e["loc"], "type": e["type"]} for e in exc.errors()]},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception",
        path=request.url.path,
        error=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Include routers
from app.api.v1.operations import router as operations_router
from app.services.crm.providers import ProviderFailure


@app.exception_handler(ProviderFailure)
async def provider_exception_handler(request: Request, exc: ProviderFailure):
    return JSONResponse(status_code=503, content={"detail": "Provider operation unavailable", "code": exc.code})


app.include_router(operations_router, prefix="/api/v1")
from app.api.v1.unsubscribe import router as unsubscribe_router
app.include_router(unsubscribe_router, prefix="/api/v1")
app.include_router(hooks_router, prefix="/api/v1")
app.include_router(foundation_router, prefix="/api/v1")
app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(companies_router, prefix="/api/v1")
app.include_router(leads_router, prefix="/api/v1")
app.include_router(firecrawl_router, prefix="/api/v1")
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
    s = _get_settings()
    return {
        "name": s.app.name,
        "version": s.app.version,
        "status": "running",
        "docs": "/docs" if s.app.debug else "disabled",
    }


if __name__ == "__main__":
    import uvicorn
    s = _get_settings()
    uvicorn.run(
        "app.main:app",
        host=s.app.host,
        port=s.app.port,
        reload=s.app.debug,
        log_config=None,  # Use structlog
    )
