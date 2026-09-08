"""
Health check API routes for Globexa CRM.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas import HealthResponse


settings = get_settings()
router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Comprehensive health check."""
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    redis_status = "healthy"
    redis_client = None
    try:
        redis_client = redis.from_url(settings.redis.url)
        await redis_client.ping()
    except Exception:
        redis_status = "unhealthy"
    finally:
        if redis_client is not None:
            await redis_client.aclose()

    overall_status = (
        "healthy"
        if db_status == "healthy" and redis_status == "healthy"
        else "degraded"
    )

    return HealthResponse(
        status=overall_status,
        version=settings.app.version,
        environment=settings.app.environment,
        database=db_status,
        redis=redis_status,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Kubernetes readiness probe with a real HTTP 503 on DB failure."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not ready"},
        )


@router.get("/live")
async def liveness_check():
    """Kubernetes liveness probe."""
    return {"status": "alive"}
