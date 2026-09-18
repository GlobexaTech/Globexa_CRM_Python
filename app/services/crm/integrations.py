import base64
import hashlib
import secrets
import copy
from datetime import timedelta
from sqlalchemy import select, delete
from fastapi import HTTPException
from app.models import (
    Integration,
    OAuthSession,
    OAuthToken,
    IntegrationCredential,
    IntegrationStatusEnum,
)
from app.services.crm.common import owned, authorize, meter, audit, now, enqueue
from app.services.crm.providers import adapter_for, ProviderFailure


async def start_oauth(db, tenant_id, actor_id, integration_id):
    await authorize(db, tenant_id, actor_id, "integrations:write")
    integration = await owned(db, Integration, tenant_id, integration_id, True)
    adapter = adapter_for(integration)
    if "oauth" not in adapter.capabilities:
        raise HTTPException(501, "Provider OAuth is unavailable")
    config = adapter.configuration()
    await meter(db, tenant_id, actor_id, "integrations")
    # Only the latest authorization flow may install credentials.
    await db.execute(delete(OAuthSession).where(
        OAuthSession.tenant_id == tenant_id, OAuthSession.integration_id == integration_id))
    state, verifier = secrets.token_urlsafe(48), secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    db.add(
        OAuthSession(
            tenant_id=tenant_id,
            actor_id=actor_id,
            integration_id=integration_id,
            state_hash=hashlib.sha256(state.encode()).hexdigest(),
            verifier=verifier,
            redirect_uri=config["redirect_uri"],
            expires_at=now() + timedelta(minutes=10),
        )
    )
    audit(
        db,
        tenant_id,
        actor_id,
        "integration.connect_started",
        "integration",
        integration_id,
    )
    return {
        "authorization_url": adapter.authorization_url(state, challenge),
        "expires_in": 600,
    }


async def finish_oauth(db, tenant_id, actor_id, integration_id, data):
    await authorize(db, tenant_id, actor_id, "integrations:write")
    integration = await owned(db, Integration, tenant_id, integration_id, True)
    session = await db.scalar(
        select(OAuthSession)
        .where(
            OAuthSession.tenant_id == tenant_id,
            OAuthSession.integration_id == integration_id,
            OAuthSession.actor_id == actor_id,
            OAuthSession.state_hash == hashlib.sha256(data.state.encode()).hexdigest(),
        )
        .with_for_update()
    )
    if not session or session.consumed_at or session.expires_at < now():
        raise HTTPException(400, "OAuth state is invalid or expired")
    session.consumed_at = now()
    verifier, redirect_uri = session.verifier, session.redirect_uri
    session_id, consumed_at = session.id, session.consumed_at
    expected_type, expected_config = integration.type, copy.deepcopy(integration.config)
    adapter = adapter_for(integration)
    # A one-use authorization code must not be retried after an ambiguous exchange.
    await db.commit()
    tokens = await adapter.connect(data.code, verifier, redirect_uri)
    # The network exchange releases database locks. Disconnect, reconfiguration,
    # a newer OAuth flow, or permission revocation must invalidate this callback.
    await authorize(db, tenant_id, actor_id, "integrations:write")
    integration = await db.scalar(select(Integration).where(
        Integration.tenant_id == tenant_id, Integration.id == integration_id
    ).with_for_update().execution_options(populate_existing=True))
    current_session = await db.scalar(select(OAuthSession).where(
        OAuthSession.tenant_id == tenant_id, OAuthSession.id == session_id,
        OAuthSession.integration_id == integration_id, OAuthSession.actor_id == actor_id
    ).with_for_update().execution_options(populate_existing=True))
    if (not integration or not current_session or current_session.consumed_at != consumed_at
            or current_session.expires_at < now() or integration.type != expected_type
            or integration.config != expected_config):
        raise HTTPException(409, "Integration changed during authorization; reconnect required")
    await store_tokens(db, tenant_id, integration, tokens)
    integration.status = IntegrationStatusEnum.CONNECTED
    audit(
        db, tenant_id, actor_id, "integration.connected", "integration", integration_id
    )
    return {"id": integration.id, "status": "connected"}


async def store_tokens(db, tenant_id, integration, tokens):
    if not tokens.get("access_token"):
        raise ProviderFailure("invalid_token_response")
    # Integration lock prevents multiple active token rows across simultaneous callbacks/refreshes.
    await owned(db, Integration, tenant_id, integration.id, True)
    row = await db.scalar(
        select(OAuthToken)
        .where(
            OAuthToken.tenant_id == tenant_id,
            OAuthToken.integration_id == integration.id,
        )
        .order_by(OAuthToken.created_at.desc())
        .limit(1)
    )
    if row is None:
        row = OAuthToken(tenant_id=tenant_id, integration_id=integration.id)
        db.add(row)
    row.access_token = tokens["access_token"]
    if tokens.get("refresh_token"):
        row.refresh_token = tokens["refresh_token"]
    row.expires_at = now() + timedelta(
        seconds=max(1, int(tokens.get("expires_in", 3600)))
    )
    if tokens.get("scope"):
        row.scopes = tokens["scope"].split()
    await db.flush()
    return row


async def access_token(db, tenant_id, integration):
    await db.flush()
    integration = await db.scalar(select(Integration).where(
        Integration.tenant_id == tenant_id, Integration.id == integration.id
    ).with_for_update().execution_options(populate_existing=True))
    if not integration or integration.status != IntegrationStatusEnum.CONNECTED:
        raise ProviderFailure("integration_disconnected")
    row = await db.scalar(
        select(OAuthToken)
        .where(
            OAuthToken.tenant_id == tenant_id,
            OAuthToken.integration_id == integration.id,
        )
        .order_by(OAuthToken.created_at.desc())
        .limit(1).execution_options(populate_existing=True)
    )
    if not row:
        import json
        credential = await db.scalar(select(IntegrationCredential).where(
            IntegrationCredential.tenant_id == tenant_id, IntegrationCredential.integration_id == integration.id,
            IntegrationCredential.is_active.is_(True)).order_by(IntegrationCredential.created_at.desc()).limit(1).execution_options(populate_existing=True))
        if not credential:
            raise ProviderFailure("credentials_missing")
        values = json.loads(credential.credentials_encrypted)
        token = credential.access_token or values.get("access_token") or values.get("api_key")
        if not token:
            raise ProviderFailure("credentials_missing")
        if credential.token_expires_at and credential.token_expires_at < now():
            raise ProviderFailure("token_expired_reconnect_required")
        return token
    if row.expires_at is not None and row.expires_at < now() + timedelta(seconds=60):
        if not row.refresh_token:
            raise ProviderFailure("token_expired_reconnect_required")
        tokens = await adapter_for(integration).refresh(row.refresh_token)
        row = await store_tokens(db, tenant_id, integration, tokens)
    return row.access_token


async def disconnect(db, tenant_id, actor_id, integration_id):
    await authorize(db, tenant_id, actor_id, "integrations:write")
    integration = await owned(db, Integration, tenant_id, integration_id, True)
    row = await db.scalar(
        select(OAuthToken)
        .where(
            OAuthToken.tenant_id == tenant_id,
            OAuthToken.integration_id == integration_id,
        )
        .limit(1)
    )
    remote_revocation = False
    if row:
        try:
            response = await adapter_for(integration).disconnect(row.access_token)
            remote_revocation = response.get("remote_revocation", False)
        except ProviderFailure:
            pass  # Local disconnect always removes access even when provider revocation is unavailable.
    for model in (OAuthToken, IntegrationCredential, OAuthSession):
        await db.execute(
            delete(model).where(
                model.tenant_id == tenant_id, model.integration_id == integration_id
            )
        )
    integration.status = IntegrationStatusEnum.DISCONNECTED
    integration.sync_enabled = False
    audit(
        db,
        tenant_id,
        actor_id,
        "integration.disconnected",
        "integration",
        integration_id,
    )
    return {"status": "disconnected", "remote_revocation": remote_revocation}


async def request_sync(db, tenant_id, actor_id, integration_id, key, cursor=None):
    await authorize(db, tenant_id, actor_id, "integrations:write")
    if cursor is not None:
        raise HTTPException(422, "Sync cursors are managed by the server")
    integration = await owned(db, Integration, tenant_id, integration_id)
    if "sync" not in adapter_for(integration).capabilities:
        raise HTTPException(501, "Provider sync is unavailable")
    job, created = await enqueue(
        db,
        tenant_id,
        actor_id,
        "sync",
        "sync:" + key,
        {"integration_id": str(integration_id)},
    )
    if created:
        from app.models import SyncJob, SyncCursor
        has_cursor = await db.scalar(select(SyncCursor.id).where(SyncCursor.tenant_id == tenant_id,
                                     SyncCursor.integration_id == integration_id, SyncCursor.cursor_type == "provider"))
        sync_job = SyncJob(tenant_id=tenant_id, integration_id=integration_id,
                          sync_type="incremental" if has_cursor else "initial", status="pending")
        db.add(sync_job)
        await db.flush()
        await meter(db, tenant_id, actor_id, "integrations")
        job.result = {"metered": True, "sync_job_id": str(sync_job.id)}
    return job
