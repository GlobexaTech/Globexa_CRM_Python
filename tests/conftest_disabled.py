"""
Test configuration and fixtures.
"""
import pytest
import asyncio
from typing import AsyncGenerator
from uuid import uuid4
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import get_db, engine, Base
from app.core.config import Settings
from app.models import Tenant, User, Membership, RoleEnum, PackageEnum, Subscription, SubscriptionStatusEnum


# Test settings
class TestSettings(Settings):
    app_env: str = "test"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/globexa_crm_test"
    redis_url: str = "redis://localhost:6379/1"
    secret_key: str = "test-secret-key-for-testing-only-32-chars-minimum"
    google_client_id: str = ""
    google_client_secret: str = ""


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    # For now, use the main database with a test schema
    # In CI, this would be a separate test database
    from sqlalchemy.ext.asyncio import create_async_engine
    test_engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/globexa_crm_test",
        poolclass=None,
    )
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield test_engine
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def db_session(test_engine):
    """Create a database session for testing."""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    
    async_session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with async_session() as session:
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
async def test_tenant(db_session) -> Tenant:
    """Create a test tenant."""
    tenant = Tenant(
        name="Test Tenant",
        slug="test-tenant",
        is_active=True,
    )
    db_session.add(tenant)
    await db_session.flush()
    
    # Create subscription
    subscription = Subscription(
        tenant_id=tenant.id,
        package=PackageEnum.STARTER,
        status=SubscriptionStatusEnum.TRIALING,
    )
    db_session.add(subscription)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest.fixture
async def test_user(db_session, test_tenant) -> User:
    """Create a test user."""
    user = User(
        email="test@example.com",
        hashed_password="$2b$12$testhashedpassword",  # bcrypt hash of "password"
        full_name="Test User",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    
    # Create membership
    membership = Membership(
        user_id=user.id,
        tenant_id=test_tenant.id,
        role=RoleEnum.OWNER,
        is_default=True,
    )
    db_session.add(membership)
    await db_session.commit()
    await db_session.refresh(user)
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