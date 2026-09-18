from sqlalchemy import update, delete
from datetime import timedelta
"""
Integration API routes for Globexa CRM.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone

from app.core.database import get_db
from app.api.deps import get_current_active_user, require_integrations_read, require_integrations_write, require_integrations_webhooks, get_tenant_id
from app.schemas import PaginationParams, PaginatedResponse
from app.models import (
    Integration, IntegrationCredential, WebhookEndpoint, IntegrationSyncLog,
    LeadSourceConfig, Touchpoint, AttributionRule, RevenueAttribution,
    User, IntegrationTypeEnum, IntegrationStatusEnum, SyncStatusEnum, OAuthSession
)
from app.services.crm.providers import adapter_for, provider_state, adapters
from app.schemas.provider_credentials import validate_credential_write

router = APIRouter(prefix="/integrations", tags=["Integrations"])

PROVIDER_CONFIG_FIELDS = {"provider", "phone_number_id", "business_account_id", "page_id", "form_id", "customer_id"}


def validate_provider_config(config):
    if not isinstance(config, dict) or set(config) - PROVIDER_CONFIG_FIELDS:
        raise HTTPException(422, "Unsupported provider configuration field; use encrypted credentials for secrets")
    if any(not isinstance(value, str) or len(value) > 255 for value in config.values()):
        raise HTTPException(422, "Provider configuration values must be bounded strings")
    if config.get("provider") and config["provider"] not in adapters:
        raise HTTPException(422, "Unsupported provider")



# =============================================================================
# Integration CRUD
# =============================================================================

@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_integration(
    data: dict,
    current_user: tuple = Depends(require_integrations_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create a new integration."""
    from app.services.crm.common import meter
    await meter(db, tenant_id, current_user[0].id, "integrations")
    user, _ = current_user

    # Validate required fields
    if not data.get("type") or not data.get("name"):
        raise HTTPException(status_code=400, detail="type and name are required")

    config = data.get("config", {})
    validate_provider_config(config)
    if not isinstance(config, dict) or any(any(word in key.lower() for word in ("secret", "token", "password", "api_key")) for key in config):
        raise HTTPException(422, "Store credentials in the encrypted credential endpoint")
    if data.get("type") not in {v.value for v in IntegrationTypeEnum}:
        raise HTTPException(422, "Unsupported integration type")
    if config.get("provider") and config["provider"] not in adapters:
        raise HTTPException(422, "Unsupported provider")
    if not isinstance(data["name"], str) or not 1 <= len(data["name"]) <= 255:
        raise HTTPException(422, "Invalid integration name")
    # Check uniqueness
    result = await db.execute(
        select(Integration).where(
            Integration.tenant_id == tenant_id,
            Integration.type == data["type"],
            Integration.name == data["name"],
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Integration with this type and name already exists")

    integration = Integration(
        tenant_id=tenant_id,
        type=data["type"],
        name=data["name"],
        description=data.get("description"),
        config=data.get("config", {}),
        sync_enabled=data.get("sync_enabled", True),
        sync_frequency_minutes=data.get("sync_frequency_minutes", 60),
        field_mappings=data.get("field_mappings", []),
        custom_fields=data.get("custom_fields", {}),
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(integration)
    await db.commit()
    await db.refresh(integration)

    return {"id": str(integration.id), "message": "Integration created"}


@router.get("", response_model=PaginatedResponse)
async def list_integrations(
    params: PaginationParams = Depends(),
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: tuple = Depends(require_integrations_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List integrations with filtering."""
    query = select(Integration).where(Integration.tenant_id == tenant_id).options(
        selectinload(Integration.credentials),
        selectinload(Integration.webhooks),
    )

    if type:
        if type not in {value.value for value in IntegrationTypeEnum}:
            raise HTTPException(422, "Unsupported integration type")
        query = query.where(Integration.type == type)
    if status:
        if status not in {value.value for value in IntegrationStatusEnum}:
            raise HTTPException(422, "Unsupported integration status")
        query = query.where(Integration.status == status)

    query = query.order_by(Integration.created_at.desc())

    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    integrations = result.scalars().all()

    return PaginatedResponse.create(
        items=[{
            "id": str(i.id),
            "type": i.type.value,
            "name": i.name,
            "description": i.description,
            "status": i.status.value,
            "provider": (i.config or {}).get("provider", i.type.value),
            "provider_state": provider_state(i),
            "capabilities": sorted(adapters.get((i.config or {}).get("provider", i.type.value), adapters["linkedin"]).capabilities) if (i.config or {}).get("provider", i.type.value) in adapters else [],
            "sync_enabled": i.sync_enabled,
            "sync_frequency_minutes": i.sync_frequency_minutes,
            "last_sync_at": i.last_sync_at,
            "last_sync_status": i.last_sync_status.value if i.last_sync_status else None,
            "records_synced": i.records_synced,
            "credentials_count": len(i.credentials),
            "webhooks_count": len(i.webhooks),
        } for i in integrations],
        total=total,
        params=params,
    )


@router.get("/{integration_id}", response_model=dict)
async def get_integration(
    integration_id: UUID,
    current_user: tuple = Depends(require_integrations_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get integration with credentials and webhooks."""
    result = await db.execute(
        select(Integration)
        .where(Integration.id == integration_id, Integration.tenant_id == tenant_id)
        .options(
            selectinload(Integration.credentials),
            selectinload(Integration.webhooks),
            selectinload(Integration.sync_logs),
            selectinload(Integration.created_by),
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    return {
        "id": str(integration.id),
        "type": integration.type.value,
        "name": integration.name,
        "description": integration.description,
        "status": integration.status.value,
        "provider": (integration.config or {}).get("provider", integration.type.value),
        "provider_state": provider_state(integration),
        "capabilities": sorted(adapter_for(integration).capabilities) if (integration.config or {}).get("provider", integration.type.value) in adapters else [],
        "config": integration.config,
        "sync_enabled": integration.sync_enabled,
        "sync_frequency_minutes": integration.sync_frequency_minutes,
        "last_sync_at": integration.last_sync_at,
        "last_sync_status": integration.last_sync_status.value if integration.last_sync_status else None,
        "last_sync_error": integration.last_sync_error,
        "records_synced": integration.records_synced,
        "field_mappings": integration.field_mappings,
        "credentials": [{
            "id": str(c.id),
            "name": c.name,
            "is_active": c.is_active,
            "last_validated_at": c.last_validated_at,
            "validation_error": c.validation_error,
        } for c in integration.credentials],
        "webhooks": [{
            "id": str(w.id),
            "name": w.name,
            "url_path": w.url_path,
            "events": w.events,
            "is_active": w.is_active,
        } for w in integration.webhooks],
        "recent_syncs": [{
            "id": str(s.id),
            "sync_type": s.sync_type,
            "status": s.status.value,
            "records_processed": s.records_processed,
            "records_created": s.records_created,
            "records_updated": s.records_updated,
            "records_failed": s.records_failed,
            "started_at": s.started_at,
            "completed_at": s.completed_at,
        } for s in integration.sync_logs],
        "created_at": integration.created_at,
        "updated_at": integration.updated_at,
    }


@router.patch("/{integration_id}", response_model=dict)
async def update_integration(
    integration_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_integrations_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update integration."""
    user, _ = current_user

    result = await db.execute(
        select(Integration).where(Integration.id == integration_id, Integration.tenant_id == tenant_id).with_for_update()
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    if "config" in data:
        cfg = data["config"]
        validate_provider_config(cfg)
        if not isinstance(cfg, dict) or any(any(word in key.lower() for word in ("secret", "token", "password", "api_key")) for key in cfg):
            raise HTTPException(422, "Store credentials in the encrypted credential endpoint")
        if cfg.get("provider") not in adapters:
            raise HTTPException(422, "Unsupported provider")
        if integration.status == IntegrationStatusEnum.CONNECTED and cfg != integration.config:
            raise HTTPException(409, "Disconnect before changing provider configuration")
        if cfg != integration.config:
            await db.execute(delete(OAuthSession).where(OAuthSession.tenant_id == tenant_id,
                             OAuthSession.integration_id == integration_id))
    update_data = data.copy()
    update_data.pop("id", None)
    update_data.pop("tenant_id", None)
    update_data.pop("created_by_id", None)
    update_data.pop("created_at", None)

    for field, value in update_data.items():
        if field in ['config', 'custom_fields', 'description', 'field_mappings', 'name', 'sync_enabled', 'sync_frequency_minutes']:
            setattr(integration, field, value)

    integration.updated_by_id = user.id
    await db.commit()
    await db.refresh(integration)

    return {"id": str(integration.id), "message": "Integration updated"}


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: UUID,
    current_user: tuple = Depends(require_integrations_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete integration."""
    result = await db.execute(
        select(Integration).where(Integration.id == integration_id, Integration.tenant_id == tenant_id)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    await db.delete(integration)
    await db.commit()


# =============================================================================
# Credentials Management
# =============================================================================

@router.post("/{integration_id}/credentials", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_credential(
    integration_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_integrations_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Add credential to integration."""
    user, _ = current_user
    data = validate_credential_write(data, creating=True)

    # Verify integration
    result = await db.execute(
        select(Integration).where(Integration.id == integration_id, Integration.tenant_id == tenant_id)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    if not isinstance(data.get("name"), str) or not 1 <= len(data["name"]) <= 255:
        raise HTTPException(422, "Credential name required")
    # Check uniqueness
    result = await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.integration_id == integration_id,
            IntegrationCredential.name == data["name"],
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Credential with this name already exists")

    # EncryptedText routes this through CredentialService at the database boundary.
    import json
    if not isinstance(data.get("name"), str) or not 1 <= len(data["name"]) <= 255:
        raise HTTPException(422, "Credential name required")
    credentials_encrypted = json.dumps(data.get("credentials", {}))
    if len(credentials_encrypted) > 16000:
        raise HTTPException(422, "Credential too large")

    credential = IntegrationCredential(
        tenant_id=tenant_id,
        integration_id=integration_id,
        name=data["name"],
        credentials_encrypted=credentials_encrypted,
        access_token=data.get("access_token"),
        refresh_token=data.get("refresh_token"),
        token_expires_at=data.get("token_expires_at"),
        token_type=data.get("token_type"),
        scopes=data.get("scopes", []),
        is_active=data.get("is_active", True),
        custom_fields=data.get("custom_fields", {}),
    )
    db.add(credential)

    # Storing bytes is not proof of provider connectivity.
    integration.status = IntegrationStatusEnum.PENDING
    await db.commit()
    await db.refresh(credential)

    return {"id": str(credential.id), "message": "Credential added"}


@router.get("/{integration_id}/credentials", response_model=List[dict])
async def list_credentials(
    integration_id: UUID,
    current_user: tuple = Depends(require_integrations_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List integration credentials (without sensitive data)."""
    result = await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.integration_id == integration_id,
            IntegrationCredential.tenant_id == tenant_id,
        )
    )
    credentials = result.scalars().all()

    return [{
        "id": str(c.id),
        "name": c.name,
        "is_active": c.is_active,
        "last_validated_at": c.last_validated_at,
        "validation_error": c.validation_error,
        "token_expires_at": c.token_expires_at,
        "token_type": c.token_type,
        "scopes": c.scopes,
    } for c in credentials]


@router.patch("/credentials/{credential_id}", response_model=dict)
async def update_credential(
    credential_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_integrations_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update credential."""
    user, _ = current_user
    data = validate_credential_write(data)

    result = await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.id == credential_id,
            IntegrationCredential.tenant_id == tenant_id,
        )
    )
    credential = result.scalar_one_or_none()
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    update_data = data.copy()
    
    # Encrypt credentials if provided
    if "credentials" in update_data:
        import json
        credential.credentials_encrypted = json.dumps(update_data.pop("credentials"))

    for field, value in update_data.items():
        if field in ['access_token', 'is_active', 'name', 'refresh_token', 'scopes', 'token_expires_at', 'token_type']:
            setattr(credential, field, value)

    if {"credentials", "access_token", "refresh_token", "token_expires_at", "is_active"} & set(data):
        integration = await owned(db, Integration, tenant_id, credential.integration_id, True)
        integration.status = IntegrationStatusEnum.PENDING
        credential.last_validated_at = None
    credential.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {"id": str(credential.id), "message": "Credential updated"}


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    credential_id: UUID,
    current_user: tuple = Depends(require_integrations_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete credential."""
    result = await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.id == credential_id,
            IntegrationCredential.tenant_id == tenant_id,
        )
    )
    credential = result.scalar_one_or_none()
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    await db.delete(credential)
    
    # Check if integration has other credentials
    integration_result = await db.execute(
        select(Integration).where(Integration.id == credential.integration_id)
    )
    integration = integration_result.scalar_one_or_none()
    if integration:
        creds_result = await db.execute(
            select(func.count()).select_from(IntegrationCredential).where(
                IntegrationCredential.integration_id == integration.id
            )
        )
        if creds_result.scalar() == 0:
            integration.status = IntegrationStatusEnum.DISCONNECTED

    await db.commit()


@router.post("/{integration_id}/validate", response_model=dict)
async def validate_integration(
    integration_id: UUID,
    current_user: tuple = Depends(require_integrations_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    from app.services.crm.common import owned
    from app.services.crm.providers import adapter_for
    from app.services.crm.integrations import access_token
    integration = await owned(db, Integration, tenant_id, integration_id)
    token = await access_token(db, tenant_id, integration)
    result = await adapter_for(integration).health_check(token)
    await db.commit()
    return result


@router.post("/{integration_id}/sync", response_model=dict)
async def sync_integration(
    integration_id: UUID,
    background_tasks: BackgroundTasks,
    full_sync: bool = Query(False),
    current_user: tuple = Depends(require_integrations_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    raise HTTPException(410, "Use /operations/integrations/{id}/sync with Idempotency-Key")


@router.get("/{integration_id}/sync-logs", response_model=PaginatedResponse)
async def list_sync_logs(
    integration_id: UUID,
    params: PaginationParams = Depends(),
    current_user: tuple = Depends(require_integrations_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List integration sync logs."""
    query = (
        select(IntegrationSyncLog)
        .where(
            IntegrationSyncLog.integration_id == integration_id,
            IntegrationSyncLog.tenant_id == tenant_id,
        )
        .order_by(IntegrationSyncLog.started_at.desc())
    )
    total_query = select(func.count()).select_from(
        select(IntegrationSyncLog).where(
            IntegrationSyncLog.integration_id == integration_id,
            IntegrationSyncLog.tenant_id == tenant_id,
        ).subquery()
    )
    total = await db.scalar(total_query)

    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    logs = result.scalars().all()

    return PaginatedResponse.create(
        items=[{
            "id": str(l.id),
            "sync_type": l.sync_type,
            "status": l.status.value,
            "records_processed": l.records_processed,
            "records_created": l.records_created,
            "records_updated": l.records_updated,
            "records_failed": l.records_failed,
            "started_at": l.started_at,
            "completed_at": l.completed_at,
            "duration_seconds": l.duration_seconds,
            "triggered_by": l.triggered_by,
        } for l in logs],
        total=total,
        params=params,
    )


# =============================================================================
# Webhook Endpoints
# =============================================================================

@router.post("/{integration_id}/webhooks", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    integration_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_integrations_webhooks),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create webhook endpoint."""
    # Verify integration
    result = await db.execute(
        select(Integration).where(Integration.id == integration_id, Integration.tenant_id == tenant_id)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    # Check URL path uniqueness
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.tenant_id == tenant_id,
            WebhookEndpoint.url_path == data["url_path"],
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Webhook URL path already exists")

    # Caller provisions the provider secret; API responses never disclose it.
    secret = data.get("secret")
    if not isinstance(secret, str) or len(secret) < 32:
        raise HTTPException(422, "A provider signing secret of at least 32 characters is required")

    import hashlib
    custom_fields = dict(data.get("custom_fields", {}))
    custom_fields.pop("verify_token", None)
    if data.get("verify_token"):
        if not isinstance(data["verify_token"], str) or not 32 <= len(data["verify_token"]) <= 256:
            raise HTTPException(422, "Verify token must contain 32 to 256 characters")
        custom_fields["verify_token_hash"] = hashlib.sha256(data["verify_token"].encode()).hexdigest()
    if not 1 <= data.get("max_retries", 3) <= 5 or not 1 <= data.get("rate_limit_per_minute", 100) <= 1000:
        raise HTTPException(422, "Invalid webhook limits")
    webhook = WebhookEndpoint(
        tenant_id=tenant_id,
        integration_id=integration_id,
        name=data["name"],
        url_path=data["url_path"],
        secret=secret,
        events=data.get("events", []),
        is_active=data.get("is_active", True),
        retry_enabled=data.get("retry_enabled", True),
        max_retries=data.get("max_retries", 3),
        rate_limit_per_minute=data.get("rate_limit_per_minute", 100),
        custom_fields=custom_fields,
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)

    return {
        "id": str(webhook.id),
        "url_path": webhook.url_path,
        "message": "Webhook created",
        "ingress_path": f"/api/v1/hooks/{webhook.id}",
    }


@router.get("/{integration_id}/webhooks", response_model=List[dict])
async def list_webhooks(
    integration_id: UUID,
    current_user: tuple = Depends(require_integrations_webhooks),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List webhook endpoints."""
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.integration_id == integration_id,
            WebhookEndpoint.tenant_id == tenant_id,
        )
    )
    webhooks = result.scalars().all()

    return [{
        "id": str(w.id),
        "name": w.name,
        "url_path": w.url_path,
        "events": w.events,
        "is_active": w.is_active,
        "retry_enabled": w.retry_enabled,
        "max_retries": w.max_retries,
        "rate_limit_per_minute": w.rate_limit_per_minute,
    } for w in webhooks]


@router.patch("/webhooks/{webhook_id}", response_model=dict)
async def update_webhook(
    webhook_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_integrations_webhooks),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update webhook endpoint."""
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == webhook_id,
            WebhookEndpoint.tenant_id == tenant_id,
        )
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    update_data = data.copy()
    for field in ["name", "events", "is_active", "retry_enabled", "max_retries", "rate_limit_per_minute", "response_template"]:
        if field in update_data:
            setattr(webhook, field, update_data[field])

    await db.commit()
    return {"id": str(webhook.id), "message": "Webhook updated"}


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: UUID,
    current_user: tuple = Depends(require_integrations_webhooks),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete webhook endpoint."""
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == webhook_id,
            WebhookEndpoint.tenant_id == tenant_id,
        )
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Deactivate locally; immutable receipts retain their endpoint relationship.
    # A local endpoint UUID is not a provider subscription ID.
    webhook.is_active = False
    await db.commit()


# =============================================================================
# Webhook Ingress (Public - requires signature verification)
# =============================================================================

# =============================================================================
# Lead Source Configs
# =============================================================================

@router.post("/lead-sources", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_lead_source(
    data: dict,
    current_user: tuple = Depends(require_integrations_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create lead source configuration."""
    user, _ = current_user

    # Check uniqueness
    result = await db.execute(
        select(LeadSourceConfig).where(
            LeadSourceConfig.tenant_id == tenant_id,
            LeadSourceConfig.source_key == data["source_key"],
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Source key already exists")

    source = LeadSourceConfig(
        tenant_id=tenant_id,
        source_key=data["source_key"],
        display_name=data["display_name"],
        description=data.get("description"),
        source_type=data["source_type"],
        default_utm_source=data.get("default_utm_source"),
        default_utm_medium=data.get("default_utm_medium"),
        default_utm_campaign=data.get("default_utm_campaign"),
        auto_create_contact=data.get("auto_create_contact", True),
        auto_create_company=data.get("auto_create_company", True),
        default_lead_status=data.get("default_lead_status", "new"),
        default_owner_id=data.get("default_owner_id"),
        deduplication_fields=data.get("deduplication_fields", ["email"]),
        icon=data.get("icon"),
        color=data.get("color"),
        is_active=data.get("is_active", True),
        sort_order=data.get("sort_order", 0),
        custom_fields=data.get("custom_fields", {}),
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    return {"id": str(source.id), "message": "Lead source created"}


@router.get("/lead-sources", response_model=List[dict])
async def list_lead_sources(
    current_user: tuple = Depends(require_integrations_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List lead source configurations."""
    result = await db.execute(
        select(LeadSourceConfig)
        .where(LeadSourceConfig.tenant_id == tenant_id)
        .order_by(LeadSourceConfig.sort_order, LeadSourceConfig.display_name)
    )
    sources = result.scalars().all()

    return [{
        "id": str(s.id),
        "source_key": s.source_key,
        "display_name": s.display_name,
        "description": s.description,
        "source_type": s.source_type.value,
        "default_utm_source": s.default_utm_source,
        "default_utm_medium": s.default_utm_medium,
        "default_utm_campaign": s.default_utm_campaign,
        "auto_create_contact": s.auto_create_contact,
        "auto_create_company": s.auto_create_company,
        "default_lead_status": s.default_lead_status,
        "deduplication_fields": s.deduplication_fields,
        "icon": s.icon,
        "color": s.color,
        "is_active": s.is_active,
        "sort_order": s.sort_order,
    } for s in sources]


@router.patch("/lead-sources/{source_id}", response_model=dict)
async def update_lead_source(
    source_id: UUID,
    data: dict,
    current_user: tuple = Depends(require_integrations_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Update lead source configuration."""
    result = await db.execute(
        select(LeadSourceConfig).where(
            LeadSourceConfig.id == source_id,
            LeadSourceConfig.tenant_id == tenant_id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Lead source not found")

    update_data = data.copy()
    update_data.pop("id", None)
    update_data.pop("tenant_id", None)
    update_data.pop("created_at", None)

    for field, value in update_data.items():
        if field in ['config', 'custom_fields', 'description', 'field_mappings', 'is_active', 'name']:
            setattr(source, field, value)

    source.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": str(source.id), "message": "Lead source updated"}


@router.delete("/lead-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead_source(
    source_id: UUID,
    current_user: tuple = Depends(require_integrations_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Delete lead source configuration."""
    result = await db.execute(
        select(LeadSourceConfig).where(
            LeadSourceConfig.id == source_id,
            LeadSourceConfig.tenant_id == tenant_id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Lead source not found")

    await db.delete(source)
    await db.commit()


# =============================================================================
# Attribution
# =============================================================================

@router.get("/attribution/touchpoints", response_model=PaginatedResponse)
async def list_touchpoints(
    params: PaginationParams = Depends(),
    contact_id: Optional[UUID] = Query(None),
    lead_id: Optional[UUID] = Query(None),
    deal_id: Optional[UUID] = Query(None),
    source: Optional[str] = Query(None),
    campaign: Optional[str] = Query(None),
    current_user: tuple = Depends(require_integrations_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List touchpoints with filtering."""
    query = select(Touchpoint).where(Touchpoint.tenant_id == tenant_id)

    if contact_id:
        query = query.where(Touchpoint.contact_id == contact_id)
    if lead_id:
        query = query.where(Touchpoint.lead_id == lead_id)
    if deal_id:
        query = query.where(Touchpoint.deal_id == deal_id)
    if source:
        query = query.where(Touchpoint.source == source)
    if campaign:
        query = query.where(Touchpoint.campaign == campaign)

    query = query.order_by(Touchpoint.occurred_at.desc())

    total_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(total_query)

    result = await db.execute(
        query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    )
    touchpoints = result.scalars().all()

    return PaginatedResponse.create(
        items=[{
            "id": str(t.id),
            "contact_id": str(t.contact_id) if t.contact_id else None,
            "lead_id": str(t.lead_id) if t.lead_id else None,
            "deal_id": str(t.deal_id) if t.deal_id else None,
            "source": t.source,
            "medium": t.medium,
            "campaign": t.campaign,
            "ad_group": t.ad_group,
            "ad_creative": t.ad_creative,
            "landing_page": t.landing_page,
            "utm_source": t.utm_source,
            "utm_medium": t.utm_medium,
            "utm_campaign": t.utm_campaign,
            "interaction_type": t.interaction_type,
            "is_first_touch": t.is_first_touch,
            "is_last_touch": t.is_last_touch,
            "attribution_weight": t.attribution_weight,
            "occurred_at": t.occurred_at,
        } for t in touchpoints],
        total=total,
        params=params,
    )


@router.post("/attribution/rules", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_attribution_rule(
    data: dict,
    current_user: tuple = Depends(require_integrations_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Create attribution rule."""
    user, _ = current_user

    # Check uniqueness
    result = await db.execute(
        select(AttributionRule).where(
            AttributionRule.tenant_id == tenant_id,
            AttributionRule.name == data["name"],
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Rule name already exists")

    rule = AttributionRule(
        tenant_id=tenant_id,
        name=data["name"],
        model=data.get("model", "last_touch"),
        lookback_days=data.get("lookback_days", 90),
        included_sources=data.get("included_sources", []),
        excluded_sources=data.get("excluded_sources", []),
        included_mediums=data.get("included_mediums", []),
        excluded_mediums=data.get("excluded_mediums", []),
        first_touch_weight=data.get("first_touch_weight", 0.4),
        last_touch_weight=data.get("last_touch_weight", 0.4),
        middle_touch_weight=data.get("middle_touch_weight", 0.2),
        half_life_days=data.get("half_life_days", 7),
        is_active=data.get("is_active", True),
        is_default=data.get("is_default", False),
        custom_fields=data.get("custom_fields", {}),
    )
    db.add(rule)

    # If set as default, unset other defaults
    if rule.is_default:
        await db.execute(
            update(AttributionRule)
            .where(AttributionRule.tenant_id == tenant_id, AttributionRule.is_default == True)
            .values(is_default=False)
        )

    await db.commit()
    await db.refresh(rule)

    return {"id": str(rule.id), "message": "Attribution rule created"}


@router.get("/attribution/rules", response_model=List[dict])
async def list_attribution_rules(
    current_user: tuple = Depends(require_integrations_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """List attribution rules."""
    result = await db.execute(
        select(AttributionRule)
        .where(AttributionRule.tenant_id == tenant_id)
        .order_by(AttributionRule.is_default.desc(), AttributionRule.name)
    )
    rules = result.scalars().all()

    return [{
        "id": str(r.id),
        "name": r.name,
        "model": r.model.value,
        "lookback_days": r.lookback_days,
        "first_touch_weight": r.first_touch_weight,
        "last_touch_weight": r.last_touch_weight,
        "middle_touch_weight": r.middle_touch_weight,
        "half_life_days": r.half_life_days,
        "is_active": r.is_active,
        "is_default": r.is_default,
    } for r in rules]


@router.get("/attribution/revenue/{deal_id}", response_model=dict)
async def get_revenue_attribution(
    deal_id: UUID,
    rule_id: Optional[UUID] = Query(None),
    current_user: tuple = Depends(require_integrations_read),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Get revenue attribution for a deal."""
    query = select(RevenueAttribution).where(
        RevenueAttribution.deal_id == deal_id,
        RevenueAttribution.tenant_id == tenant_id,
    )
    
    if rule_id:
        query = query.where(RevenueAttribution.attribution_rule_id == rule_id)
    else:
        # Get default rule
        rule_result = await db.execute(
            select(AttributionRule).where(
                AttributionRule.tenant_id == tenant_id,
                AttributionRule.is_default == True,
            )
        )
        default_rule = rule_result.scalar_one_or_none()
        if default_rule:
            query = query.where(RevenueAttribution.attribution_rule_id == default_rule.id)

    result = await db.execute(query)
    attribution = result.scalar_one_or_none()
    
    if not attribution:
        return {"message": "No attribution calculated for this deal"}

    return {
        "id": str(attribution.id),
        "deal_id": str(attribution.deal_id),
        "attribution_rule_id": str(attribution.attribution_rule_id),
        "attributed_revenue": attribution.attributed_revenue,
        "by_source": attribution.by_source,
        "by_medium": attribution.by_medium,
        "by_campaign": attribution.by_campaign,
        "touchpoint_attributions": attribution.touchpoint_attributions,
        "calculated_at": attribution.calculated_at,
    }


@router.post("/attribution/calculate/{deal_id}", response_model=dict)
async def calculate_attribution(
    deal_id: UUID,
    rule_id: Optional[UUID] = Query(None),
    current_user: tuple = Depends(require_integrations_write),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Calculate revenue attribution for a deal."""
    # Get deal
    from app.models import Deal
    deal_result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
    )
    deal = deal_result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # Get attribution rule
    if rule_id:
        rule_result = await db.execute(
            select(AttributionRule).where(AttributionRule.id == rule_id)
        )
    else:
        rule_result = await db.execute(
            select(AttributionRule).where(
                AttributionRule.tenant_id == tenant_id,
                AttributionRule.is_default == True,
            )
        )
    rule = rule_result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Attribution rule not found")

    # Get touchpoints for this deal/contact
    lookback_cutoff = datetime.now(timezone.utc) - timedelta(days=rule.lookback_days)
    
    touchpoint_query = select(Touchpoint).where(
        Touchpoint.tenant_id == tenant_id,
        Touchpoint.occurred_at >= lookback_cutoff,
    )
    
    if deal.contact_id:
        touchpoint_query = touchpoint_query.where(Touchpoint.contact_id == deal.contact_id)
    
    # Filter by sources/mediums
    if rule.included_sources:
        touchpoint_query = touchpoint_query.where(Touchpoint.source.in_(rule.included_sources))
    if rule.excluded_sources:
        touchpoint_query = touchpoint_query.where(~Touchpoint.source.in_(rule.excluded_sources))
    if rule.included_mediums:
        touchpoint_query = touchpoint_query.where(Touchpoint.medium.in_(rule.included_mediums))
    if rule.excluded_mediums:
        touchpoint_query = touchpoint_query.where(~Touchpoint.medium.in_(rule.excluded_mediums))

    touchpoint_result = await db.execute(touchpoint_query.order_by(Touchpoint.occurred_at))
    touchpoints = touchpoint_result.scalars().all()

    if not touchpoints:
        return {"message": "No touchpoints found for attribution"}

    # Calculate attribution based on model
    deal_value = deal.value or 0
    attribution_results = []

    if rule.model.value == "first_touch":
        # First touch gets 100%
        first_tp = min(touchpoints, key=lambda t: t.occurred_at)
        attribution_results.append({
            "touchpoint_id": str(first_tp.id),
            "source": first_tp.source,
            "medium": first_tp.medium,
            "campaign": first_tp.campaign,
            "weight": 1.0,
            "attributed_revenue": deal_value,
        })
    elif rule.model.value == "last_touch":
        # Last touch gets 100%
        last_tp = max(touchpoints, key=lambda t: t.occurred_at)
        attribution_results.append({
            "touchpoint_id": str(last_tp.id),
            "source": last_tp.source,
            "medium": last_tp.medium,
            "campaign": last_tp.campaign,
            "weight": 1.0,
            "attributed_revenue": deal_value,
        })
    elif rule.model.value == "linear":
        # Equal weight
        weight = 1.0 / len(touchpoints)
        for tp in touchpoints:
            attribution_results.append({
                "touchpoint_id": str(tp.id),
                "source": tp.source,
                "medium": tp.medium,
                "campaign": tp.campaign,
                "weight": weight,
                "attributed_revenue": int(deal_value * weight),
            })
    elif rule.model.value == "time_decay":
        # Exponential decay based on half-life
        import math
        total_weight = 0
        weights = []
        for tp in touchpoints:
            days_ago = (datetime.now(timezone.utc) - tp.occurred_at).days
            weight = math.exp(-days_ago * math.log(2) / rule.half_life_days)
            weights.append(weight)
            total_weight += weight
        
        for tp, weight in zip(touchpoints, weights):
            normalized_weight = weight / total_weight if total_weight > 0 else 0
            attribution_results.append({
                "touchpoint_id": str(tp.id),
                "source": tp.source,
                "medium": tp.medium,
                "campaign": tp.campaign,
                "weight": normalized_weight,
                "attributed_revenue": int(deal_value * normalized_weight),
            })
    elif rule.model.value in ["u_shaped", "w_shaped"]:
        # U-shaped: 40% first, 40% last, 20% middle
        # W-shaped: 30% first, 30% last, 30% middle (creation), 10% other
        n = len(touchpoints)
        if n == 1:
            attribution_results.append({
                "touchpoint_id": str(touchpoints[0].id),
                "source": touchpoints[0].source,
                "medium": touchpoints[0].medium,
                "campaign": touchpoints[0].campaign,
                "weight": 1.0,
                "attributed_revenue": deal_value,
            })
        elif n == 2:
            for i, tp in enumerate(touchpoints):
                weight = rule.first_touch_weight if i == 0 else rule.last_touch_weight
                attribution_results.append({
                    "touchpoint_id": str(tp.id),
                    "source": tp.source,
                    "medium": tp.medium,
                    "campaign": tp.campaign,
                    "weight": weight,
                    "attributed_revenue": int(deal_value * weight),
                })
        else:
            for i, tp in enumerate(touchpoints):
                if i == 0:
                    weight = rule.first_touch_weight
                elif i == n - 1:
                    weight = rule.last_touch_weight
                else:
                    weight = rule.middle_touch_weight / (n - 2) if n > 2 else 0
                attribution_results.append({
                    "touchpoint_id": str(tp.id),
                    "source": tp.source,
                    "medium": tp.medium,
                    "campaign": tp.campaign,
                    "weight": weight,
                    "attributed_revenue": int(deal_value * weight),
                })
    else:
        # Custom - use attribution_weight from touchpoints
        total_weight = sum(tp.attribution_weight for tp in touchpoints)
        for tp in touchpoints:
            weight = tp.attribution_weight / total_weight if total_weight > 0 else 0
            attribution_results.append({
                "touchpoint_id": str(tp.id),
                "source": tp.source,
                "medium": tp.medium,
                "campaign": tp.campaign,
                "weight": weight,
                "attributed_revenue": int(deal_value * weight),
            })

    # Aggregate by source/medium/campaign
    by_source = {}
    by_medium = {}
    by_campaign = {}
    for ar in attribution_results:
        src = ar["source"]
        med = ar["medium"]
        camp = ar["campaign"] or "unknown"
        rev = ar["attributed_revenue"]
        by_source[src] = by_source.get(src, 0) + rev
        by_medium[med] = by_medium.get(med, 0) + rev
        by_campaign[camp] = by_campaign.get(camp, 0) + rev

    # Save or update revenue attribution
    existing_result = await db.execute(
        select(RevenueAttribution).where(
            RevenueAttribution.deal_id == deal_id,
            RevenueAttribution.attribution_rule_id == rule.id,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.attributed_revenue = deal_value
        existing.touchpoint_attributions = attribution_results
        existing.by_source = by_source
        existing.by_medium = by_medium
        existing.by_campaign = by_campaign
        existing.calculated_at = datetime.now(timezone.utc)
    else:
        attribution = RevenueAttribution(
            tenant_id=tenant_id,
            deal_id=deal_id,
            attribution_rule_id=rule.id,
            attributed_revenue=deal_value,
            touchpoint_attributions=attribution_results,
            by_source=by_source,
            by_medium=by_medium,
            by_campaign=by_campaign,
        )
        db.add(attribution)

    await db.commit()

    return {
        "deal_id": str(deal_id),
        "rule_id": str(rule.id),
        "attributed_revenue": deal_value,
        "touchpoints_count": len(touchpoints),
        "attribution_results": attribution_results,
        "by_source": by_source,
        "by_medium": by_medium,
        "by_campaign": by_campaign,
    }

# Checkpoint 5 provider operational surfaces; no secret or provider cursor is returned.
from pydantic import BaseModel, ConfigDict, Field
from app.models import SyncJob, WebhookReceipt, Contact
from app.services.crm.common import owned, authorize, audit, now


class ConfigureProviderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential_id: UUID


@router.post("/{integration_id}/configure", response_model=dict)
async def configure_provider(integration_id: UUID, data: ConfigureProviderInput,
                             current_user: tuple = Depends(require_integrations_write),
                             db: AsyncSession = Depends(get_db), tenant_id: UUID = Depends(get_tenant_id)):
    import json
    integration = await owned(db, Integration, tenant_id, integration_id, True)
    adapter = adapter_for(integration)
    if "configure" not in adapter.capabilities:
        raise HTTPException(501, "This provider requires OAuth")
    credential = await owned(db, IntegrationCredential, tenant_id, data.credential_id, True)
    if credential.integration_id != integration.id or not credential.is_active:
        raise HTTPException(404, "Credential not found")
    values = json.loads(credential.credentials_encrypted)
    token = credential.access_token or values.get("access_token") or values.get("api_key")
    if not isinstance(token, str) or not token:
        raise HTTPException(422, "Access credential required")
    result = await adapter.health_check(token)
    if result.get("connected") is not True:
        raise HTTPException(409, "Provider health check failed")
    integration.status = IntegrationStatusEnum.CONNECTED
    await db.execute(update(IntegrationCredential).where(IntegrationCredential.tenant_id == tenant_id,
        IntegrationCredential.integration_id == integration.id, IntegrationCredential.id != credential.id).values(is_active=False))
    credential.last_validated_at, credential.validation_error = now(), None
    audit(db, tenant_id, current_user[0].id, "integration.connected", "integration", integration.id)
    await db.commit()
    return {"id": integration.id, "status": "connected", "provider_state": "connected", **result}


@router.get("/{integration_id}/sync-jobs", response_model=list[dict])
async def list_provider_sync_jobs(integration_id: UUID, limit: int = Query(50, ge=1, le=100),
                                  current_user: tuple = Depends(require_integrations_read),
                                  db: AsyncSession = Depends(get_db), tenant_id: UUID = Depends(get_tenant_id)):
    await owned(db, Integration, tenant_id, integration_id)
    rows = (await db.scalars(select(SyncJob).where(SyncJob.tenant_id == tenant_id, SyncJob.integration_id == integration_id)
                             .order_by(SyncJob.created_at.desc()).limit(limit))).all()
    return [{key: getattr(row, key) for key in ("id", "integration_id", "sync_type", "status", "records_processed", "records_created", "records_updated", "records_failed", "started_at", "finished_at")} | {"error_code": row.error_message} for row in rows]


@router.post("/sync-jobs/{sync_id}/cancel", response_model=dict)
async def cancel_provider_sync(sync_id: UUID, current_user: tuple = Depends(require_integrations_write),
                               db: AsyncSession = Depends(get_db), tenant_id: UUID = Depends(get_tenant_id)):
    row = await owned(db, SyncJob, tenant_id, sync_id, True)
    if row.status not in {"pending", "running", "partial"}:
        raise HTTPException(409, "Sync is already terminal")
    row.status, row.finished_at = "cancelled", now()
    audit(db, tenant_id, current_user[0].id, "integration.sync_cancelled", "sync_job", row.id)
    await db.commit()
    return {"id": row.id, "status": row.status}


@router.get("/{integration_id}/webhook-receipts", response_model=list[dict])
async def list_provider_receipts(integration_id: UUID, limit: int = Query(50, ge=1, le=100),
                                 current_user: tuple = Depends(require_integrations_read),
                                 db: AsyncSession = Depends(get_db), tenant_id: UUID = Depends(get_tenant_id)):
    await owned(db, Integration, tenant_id, integration_id)
    rows = (await db.scalars(select(WebhookReceipt).join(WebhookEndpoint, WebhookEndpoint.id == WebhookReceipt.webhook_id)
                             .where(WebhookReceipt.tenant_id == tenant_id, WebhookEndpoint.integration_id == integration_id)
                             .order_by(WebhookReceipt.created_at.desc()).limit(limit))).all()
    return [{key: getattr(row, key) for key in ("id", "state", "attempts", "error_code", "created_at", "processed_at")} for row in rows]


class EnrichmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_id: UUID | None = None
    lead_id: UUID | None = None


@router.post("/{integration_id}/enrich", response_model=dict)
async def enrich_contact(integration_id: UUID, data: EnrichmentInput,
                         current_user: tuple = Depends(require_integrations_write),
                         db: AsyncSession = Depends(get_db), tenant_id: UUID = Depends(get_tenant_id)):
    from app.services.crm.integrations import access_token
    await authorize(db, tenant_id, current_user[0].id, "contacts:write")
    if bool(data.contact_id) == bool(data.lead_id):
        raise HTTPException(422, "Choose exactly one contact or lead")
    lead = None
    contact_id = data.contact_id
    if data.lead_id:
        from app.models import Lead
        await authorize(db, tenant_id, current_user[0].id, "leads:write")
        lead = await owned(db, Lead, tenant_id, data.lead_id, True)
        contact_id = lead.contact_id
        if not contact_id:
            raise HTTPException(422, "Lead requires a linked contact with email")
    integration = await owned(db, Integration, tenant_id, integration_id, True)
    contact = await owned(db, Contact, tenant_id, contact_id, True)
    adapter = adapter_for(integration)
    if "enrich" not in adapter.capabilities:
        raise HTTPException(501, "Provider enrichment unavailable")
    if not contact.email:
        raise HTTPException(422, "Contact email required")
    result = await adapter.enrich(await access_token(db, tenant_id, integration), {"email": contact.email})
    # Enrichment is provenance-tagged supplemental data, never an unreviewed identity merge.
    contact.custom_fields = {**(contact.custom_fields or {}), "enrichment": result}
    audit(db, tenant_id, current_user[0].id, "contact.enriched", "contact", contact.id)
    if lead:
        lead.custom_fields = {**(lead.custom_fields or {}), "enrichment": result}
        audit(db, tenant_id, current_user[0].id, "lead.enriched", "lead", lead.id)
    await db.commit()
    return result


@router.post("/{integration_id}/sync-reset", response_model=dict)
async def reset_provider_sync(integration_id: UUID, current_user: tuple = Depends(require_integrations_write),
                              db: AsyncSession = Depends(get_db), tenant_id: UUID = Depends(get_tenant_id)):
    from app.models import SyncCursor, OperationJob
    from sqlalchemy import delete
    from app.services.crm.common import serial_key
    integration = await owned(db, Integration, tenant_id, integration_id, True)
    if "sync" not in adapter_for(integration).capabilities:
        raise HTTPException(501, "Provider sync unavailable")
    await serial_key(db, tenant_id, "sync:" + str(integration_id))
    active = await db.scalar(select(OperationJob.id).where(OperationJob.tenant_id == tenant_id,
        OperationJob.kind == "sync", OperationJob.payload["integration_id"].astext == str(integration_id),
        OperationJob.status.in_(["pending", "retry", "running"])).limit(1))
    if active:
        raise HTTPException(409, "Cancel or finish the current sync before resetting")
    await db.execute(delete(SyncCursor).where(SyncCursor.tenant_id == tenant_id, SyncCursor.integration_id == integration_id))
    audit(db, tenant_id, current_user[0].id, "integration.sync_reset", "integration", integration_id)
    await db.commit()
    return {"id": integration_id, "next_sync_type": "initial"}
