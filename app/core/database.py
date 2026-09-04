"""Database configuration and session management for Globexa CRM.
Uses SQLAlchemy 2.0 async with asyncpg."""
from contextlib import asynccontextmanager
from typing import Type, TypeVar, AsyncGenerator
from enum import Enum as PyEnum
from uuid import UUID

from sqlalchemy import text
from sqlalchemy import Enum as PGEnum
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.db_session import engine, AsyncSessionLocal, create_engine
from app.core.tenant_context import set_tenant_context, clear_tenant_context, tenant_db_context, get_tenant_db


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