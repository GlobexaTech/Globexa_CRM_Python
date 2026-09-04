"""Database session factory - isolated to avoid circular imports."""
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


settings = get_settings()

# Create async engine
def create_engine():
    """Create async database engine."""
    use_null_pool = settings.app.environment in ("test", "development")
    
    kwargs = {
        "url": settings.database.url,
        "pool_recycle": settings.database.pool_recycle,
        "pool_pre_ping": True,
        "echo": settings.database.echo,
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