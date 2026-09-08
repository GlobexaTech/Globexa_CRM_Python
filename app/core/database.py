"""
Database configuration and session management for Globexa CRM.
Uses SQLAlchemy 2.0 async with asyncpg.
"""
from contextlib import asynccontextmanager
from typing import Type, TypeVar, AsyncGenerator
from enum import Enum as PyEnum

from sqlalchemy import text
from sqlalchemy import Enum as PGEnum
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


E = TypeVar("E", bound=PyEnum)


def pg_enum(enum_cls: Type[E], name: str) -> PGEnum:
    """Create a PostgreSQL-native enum that stores .value, not member name."""
    return PGEnum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [item.value for item in cls],
        native_enum=True,
        create_type=False,  # Alembic creates the type
    )


settings = get_settings()

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Create async engine
def create_engine() -> AsyncEngine:
    """Create async database engine."""
    # Use NullPool for worker processes to avoid connection pooling issues with forking
    # In production, you might want to use a proper connection pool
    use_null_pool = settings.app.environment in ("test", "testing", "development")
    
    kwargs = {
        "url": settings.database.url,
        "pool_recycle": settings.database.pool_recycle,
        "pool_pre_ping": True,
        "echo": settings.database.echo,
        "hide_parameters": True,
    }
    
    if not use_null_pool:
        kwargs.update({
            "pool_size": settings.database.pool_size,
            "max_overflow": settings.database.max_overflow,
            "pool_timeout": settings.database.pool_timeout,
        })
    else:
        kwargs["poolclass"] = NullPool
    
    return create_async_engine(**kwargs)


engine = create_engine()

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database session outside of FastAPI requests."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database - just verify connection, don't create tables (Alembic manages schema)."""
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
        if settings.app.environment == "production":
            unsafe = await conn.scalar(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user"))
            if unsafe:
                raise RuntimeError("Runtime database role must not be SUPERUSER or BYPASSRLS")


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()


# For Alembic migrations
def get_sync_engine():
    """Get synchronous engine for Alembic."""
    from sqlalchemy import create_engine as create_sync_engine
    return create_sync_engine(
        settings.database.sync_url,
        poolclass=NullPool,
    )
# Install security and outbox lifecycle listeners for all Session instances.
from app.core import tenant_context  # noqa: F401,E402

from app.core import events  # noqa: F401,E402
