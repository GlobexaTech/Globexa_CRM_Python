"""
Celery Tenant Isolation

Ensures all Celery tasks establish proper tenant context before
database operations. Provides decorators and utilities for
tenant-scoped background tasks.
"""

from contextlib import asynccontextmanager
from functools import wraps
from typing import Callable, Optional, Any, TypeVar
from uuid import UUID

from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import tenant_db_context, TenantContext
from app.core.audit_log import audit_logger, AuditEventType


F = TypeVar('F', bound=Callable[..., Any])


@asynccontextmanager
async def celery_tenant_context(tenant_id: UUID) -> AsyncSession:
    """
    Context manager for Celery tasks that need tenant-scoped database access.
    
    Establishes RLS tenant context and provides a database session.
    
    Usage:
        @shared_task
        async def my_task(tenant_id: str):
            async with celery_tenant_context(UUID(tenant_id)) as db:
                # All queries here are tenant-isolated by RLS
                result = await db.execute(select(Contact))
    """
    async with tenant_db_context(tenant_id) as session:
        yield session


def tenant_task(func: F) -> F:
    """
    Decorator for Celery tasks that require tenant context.
    
    The decorated task must accept `tenant_id` as its first argument.
    Automatically establishes RLS tenant context for the task duration.
    
    Usage:
        @shared_task
        @tenant_task
        async def process_integration_sync(tenant_id: str, integration_id: str):
            async with tenant_db_context(UUID(tenant_id)) as db:
                ...
    """
    @wraps(func)
    async def wrapper(tenant_id: str, *args, **kwargs):
        async with celery_tenant_context(UUID(tenant_id)) as db:
            return await func(tenant_id, db, *args, **kwargs)
    return wrapper  # type: ignore


def tenant_task_with_tenant(func: F) -> F:
    """
    Decorator for Celery tasks that need tenant context and explicit tenant parameter.
    
    The decorated task receives (tenant_id, db, *args, **kwargs).
    """
    @wraps(func)
    async def wrapper(tenant_id: str, *args, **kwargs):
        async with celery_tenant_context(UUID(tenant_id)) as db:
            return await func(tenant_id, db, *args, **kwargs)
    return wrapper  # type: ignore


class CeleryTenantMixin:
    """
    Mixin for Celery tasks that need tenant isolation.
    
    Subclasses should implement `run_with_tenant(tenant_id: UUID, db: AsyncSession, ...)`
    """
    
    async def run(self, tenant_id: str, *args, **kwargs):
        """Entry point - establishes tenant context and calls run_with_tenant."""
        async with celery_tenant_context(UUID(tenant_id)) as db:
            return await self.run_with_tenant(UUID(tenant_id), db, *args, **kwargs)
    
    async def run_with_tenant(self, tenant_id: UUID, db: AsyncSession, *args, **kwargs):
        """Override this method in subclasses."""
        raise NotImplementedError


# Celery task base class for tenant-scoped tasks
class TenantTask:
    """
    Base class for tenant-scoped Celery tasks.
    
    Usage:
        class MyTask(TenantTask):
            async def run_with_tenant(self, tenant_id: UUID, db: AsyncSession, ...):
                ...
        
        my_task = MyTask()
        @shared_task(base=my_task)
        def process_tenant_task(tenant_id: str, ...):
            return my_task.run(tenant_id, ...)
    """
    
    def __init__(self):
        self.tenant_id: Optional[UUID] = None
        self.db: Optional[AsyncSession] = None
    
    async def setup(self, tenant_id: UUID) -> None:
        """Setup tenant context."""
        self.tenant_id = tenant_id
        self.db = await TenantContext.set_tenant_id(tenant_id)
    
    async def teardown(self) -> None:
        """Teardown tenant context."""
        if self.db:
            await self.db.close()
        self.tenant_id = None
        self.db = None
    
    async def run_with_tenant(self, tenant_id: UUID, db: AsyncSession, *args, **kwargs):
        """Override in subclass."""
        raise NotImplementedError


# Utility for getting current tenant in Celery task
async def get_current_tenant_id() -> Optional[UUID]:
    """Get current tenant ID from task context if set."""
    # This would be set by the task wrapper
    return None


# Task signature for type hints
TenantTaskSignature = Callable[[str], Any]


# Validation for task arguments
def validate_tenant_task_args(tenant_id: str, *required_args: str) -> None:
    """Validate that required arguments are provided for tenant task."""
    if not tenant_id:
        raise ValueError("tenant_id is required for tenant-scoped task")
    
    try:
        UUID(tenant_id)
    except ValueError:
        raise ValueError("tenant_id must be a valid UUID")


# Celery signal handlers for audit logging
from celery.signals import task_prerun, task_postrun, task_failure


@task_prerun.connect
def celery_task_prerun(sender=None, task_id=None, task=None, args=None, kwargs=None, **_):
    """Log task start for audit."""
    # Could log to audit if needed
    pass


@task_postrun.connect
def celery_task_postrun(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **_):
    """Log task completion for audit."""
    # Could log to audit if needed
    pass


@task_failure.connect
def celery_task_failure(sender=None, task_id=None, task=None, args=None, kwargs=None, einfo=None, **_):
    """Log task failure for audit."""
    # Could log to audit if needed
    pass


# Helper to create tenant-scoped task with proper typing
def create_tenant_task(
    name: str,
    func: Callable,
    bind: bool = False,
    **task_options
):
    """
    Factory to create a tenant-scoped Celery task with proper typing.
    
    Usage:
        @create_tenant_task("my_task")
        async def my_task(tenant_id: str, db: AsyncSession, integration_id: str):
            ...
    """
    @shared_task(bind=bind, name=name, **task_options)
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # First arg is tenant_id
        if not args:
            raise ValueError("tenant_id is required")
        
        tenant_id = args[0]
        validate_tenant_task_args(tenant_id)
        
        async with celery_tenant_context(UUID(tenant_id)) as db:
            return await func(*args, db=db, **kwargs)
    
    return wrapper


# Example usage pattern for existing tasks
"""
# In app/workers/tasks/integration_tasks.py

@create_tenant_task("integration.sync")
async def sync_integration_task(tenant_id: str, db: AsyncSession, integration_id: str, full_sync: bool = False):
    # All DB operations here are tenant-isolated
    from app.services.integration import IntegrationService
    service = IntegrationService(db)
    return await service.sync(UUID(integration_id), full_sync=full_sync)

@create_tenant_task("webhook.process")
async def process_webhook_task(tenant_id: str, db: AsyncSession, webhook_id: str, payload: dict):
    from app.services.webhook import WebhookService
    service = WebhookService(db)
    return await service.process(UUID(webhook_id), payload)
"""