import base64
import hashlib
import secrets
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
    if "connect" not in adapter.capabilities:
        raise HTTPException(501, "Provider OAuth is unavailable")
    config = adapter.configuration()
    await meter(db, tenant_id, actor_id, "integrations")
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
    # A one-use authorization code must not be retried after an ambiguous exchange.
    await db.commit()
    tokens = await adapter_for(integration).connect(data.code, verifier, redirect_uri)
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
    await owned(db, Integration, tenant_id, integration.id, True)
    if integration.status != IntegrationStatusEnum.CONNECTED:
        raise ProviderFailure("integration_disconnected")
    row = await db.scalar(
        select(OAuthToken)
        .where(
            OAuthToken.tenant_id == tenant_id,
            OAuthToken.integration_id == integration.id,
        )
        .order_by(OAuthToken.created_at.desc())
        .limit(1)
    )
    if not row:
        raise ProviderFailure("credentials_missing")
    if row.expires_at is None or row.expires_at < now() + timedelta(seconds=60):
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
    integration = await owned(db, Integration, tenant_id, integration_id)
    if "sync" not in adapter_for(integration).capabilities:
        raise HTTPException(501, "Provider sync is unavailable")
    job, created = await enqueue(
        db,
        tenant_id,
        actor_id,
        "sync",
        "sync:" + key,
        {"integration_id": str(integration_id), "cursor": cursor},
    )
    if created:
        await meter(db, tenant_id, actor_id, "integrations")
        job.result = {"metered": True}
    return job
