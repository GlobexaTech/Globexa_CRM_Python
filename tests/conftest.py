"""
Integration-test fixtures for the migrated Globexa CRM runtime.

Tests use the configured PostgreSQL database inside one outer transaction per
test. Application commits are isolated with savepoints and rolled back after
each test, so Alembic remains the schema authority and test data never persists.
"""
from typing import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import (
    Membership,
    PackageEnum,
    RoleEnum,
    Subscription,
    SubscriptionStatusEnum,
    Tenant,
    User,
)
import app.middleware.tenant as tenant_middleware


# pytest-asyncio uses a fresh event loop for each test by default. A pooled
# asyncpg connection is bound to the loop that created it and therefore cannot
# be reused safely by a later test loop. NullPool keeps the production pool
# untouched while ensuring every test gets a connection created on its own loop.
test_engine = create_async_engine(
    get_settings().database.url,
    poolclass=NullPool,
    echo=False,
)


@pytest_asyncio.fixture
async def db_connection() -> AsyncGenerator[AsyncConnection, None]:
    """Open an isolated outer transaction against the migrated test database."""
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            if transaction.is_active:
                await transaction.rollback()


@pytest_asyncio.fixture
async def db_session(
    db_connection: AsyncConnection,
) -> AsyncGenerator[AsyncSession, None]:
    """Create a session whose commits stay inside the test transaction."""
    session_factory = async_sessionmaker(
        bind=db_connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    db_connection: AsyncConnection,
    monkeypatch,
) -> AsyncGenerator[AsyncClient, None]:
    """Create an API client using the same isolated database transaction."""
    middleware_session_factory = async_sessionmaker(
        bind=db_connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(
        tenant_middleware,
        "AsyncSessionLocal",
        middleware_session_factory,
    )

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_tenant(db_session: AsyncSession) -> Tenant:
    """Create the primary tenant for a test."""
    tenant = Tenant(
        name="Test Tenant",
        slug="test-tenant",
        is_active=True,
    )
    db_session.add(tenant)
    await db_session.flush()

    subscription = Subscription(
        tenant_id=tenant.id,
        package=PackageEnum.STARTER,
        status=SubscriptionStatusEnum.TRIALING,
    )
    db_session.add(subscription)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_tenant: Tenant) -> User:
    """Create an active owner with a real bcrypt password hash."""
    user = User(
        email="test@example.com",
        hashed_password=hash_password("password"),
        full_name="Test User",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

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


@pytest_asyncio.fixture
async def auth_headers(test_user: User, test_tenant: Tenant) -> dict[str, str]:
    """Create authenticated headers bound to the fixture tenant."""
    token = create_access_token(
        {
            "sub": str(test_user.id),
            "tenant_id": str(test_tenant.id),
            "role": RoleEnum.OWNER.value,
            "email": test_user.email,
        }
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": str(test_tenant.id),
    }
