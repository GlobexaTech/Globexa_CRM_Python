"""Test configuration and fixtures."""
import pytest
import asyncio
from typing import AsyncGenerator
from uuid import uuid4
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.core.database import get_db, Base
from app.core.config import Settings, get_settings
from app.models import Tenant, User, Membership, RoleEnum, PackageEnum, Subscription, SubscriptionStatusEnum


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Mock Redis for tests
@pytest.fixture(autouse=True)
def mock_redis():
    """Mock Redis for all tests."""
    with patch("app.core.redis.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=0)
        mock_redis.zadd = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.exists = AsyncMock(return_value=0)
        mock_redis.zrange = AsyncMock(return_value=[])
        mock_redis.close = AsyncMock()
        mock_get_redis.return_value = mock_redis
        yield mock_redis


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine - using SQLite in-memory."""
    # Clear any cached settings first
    get_settings.cache_clear()
    
    # Set test environment variables BEFORE importing anything that uses settings
    import os
    os.environ["SECURITY__SECRET_KEY"] = "test-secret-key-for-testing-only-32-chars-minimum"
    os.environ["APP__ENVIRONMENT"] = "test"
    os.environ["DATABASE__HOST"] = "localhost"
    os.environ["DATABASE__PORT"] = "5432"
    os.environ["DATABASE__USERNAME"] = "postgres"
    os.environ["DATABASE__PASSWORD"] = "postgres"
    os.environ["DATABASE__NAME"] = "test_db"
    os.environ["DATABASE__URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["REDIS__URL"] = "redis://localhost:6379/1"
    os.environ["FIRECRAWL__API_KEY"] = ""
    
    # Create fresh settings with test config
    settings = Settings.from_yaml()
    
    # Use SQLite directly for tests
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool
    
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    
    # Create tables that are compatible with SQLite
    # We'll skip tables with PostgreSQL-specific types for now
    async with test_engine.begin() as conn:
        # Only create tables without JSONB/UUID types
        # This is a subset for basic testing
        pass
    
    yield test_engine
    
    await test_engine.dispose()


@pytest.fixture
async def db_session():
    """Create a mock database session for testing."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()
    session.close = AsyncMock()
    yield session


@pytest.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database override."""
    from app.core.database import AsyncSessionLocal
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()


@pytest.fixture
async def test_tenant():
    """Create a mock test tenant."""
    tenant = Tenant(
        name="Test Tenant",
        slug="test-tenant",
        is_active=True,
        id=uuid4(),
    )
    return tenant


@pytest.fixture
async def test_user(test_tenant) -> User:
    """Create a mock test user."""
    user = User(
        email="test@example.com",
        hashed_password="$2b$12$testhashedpassword",
        full_name="Test User",
        is_active=True,
        email_verified=True,
        id=uuid4(),
    )
    return user


@pytest.fixture
async def auth_headers(client, test_user, test_tenant) -> dict:
    """Get auth headers for test user."""
    from app.core.security import create_access_token
    
    token = create_access_token({
        "sub": str(test_user.id),
        "tenant_id": str(test_tenant.id),
        "role": RoleEnum.OWNER.value,
        "email": test_user.email,
    })
    return {"Authorization": f"Bearer {token}"}