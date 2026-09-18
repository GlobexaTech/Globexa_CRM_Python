"""Authentication rejects expired, substituted and revoked identities server-side."""

from datetime import timedelta
from uuid import uuid4
import jwt
import pytest
from sqlalchemy import select, delete
from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models import Membership, RoleEnum


@pytest.mark.parametrize(
    "kind", ["expired", "missing_exp", "wrong_algorithm", "wrong_signature", "wrong_type"]
)
def test_jwt_validation_rejects_invalid_tokens(kind):
    settings = get_settings()
    payload = {
        "sub": str(uuid4()),
        "tenant_id": str(uuid4()),
        "type": "access",
        "jti": uuid4().hex,
        "sid": uuid4().hex,
        "session_exp": 9999999999,
    }
    if kind == "expired":
        token = create_access_token(payload, expires_delta=timedelta(seconds=-1))
    elif kind == "missing_exp":
        token = jwt.encode(
            payload, settings.security.secret_key, algorithm=settings.security.algorithm
        )
    elif kind == "wrong_algorithm":
        token = jwt.encode(
            {**payload, "exp": 9999999999},
            settings.security.secret_key,
            algorithm="HS384" if settings.security.algorithm != "HS384" else "HS256",
        )
    elif kind == "wrong_signature":
        token = jwt.encode(
            {**payload, "exp": 9999999999},
            uuid4().hex + uuid4().hex,
            algorithm=settings.security.algorithm,
        )
    else:
        token = jwt.encode(
            {**payload, "exp": 9999999999, "sub": {"invalid": "subject"}},
            settings.security.secret_key,
            algorithm=settings.security.algorithm,
        )
    assert decode_token(token) is None


async def test_expired_refresh_and_access_token_cannot_refresh(client, test_user, test_tenant):
    payload = {"sub": str(test_user.id), "tenant_id": str(test_tenant.id), "role": "owner"}
    for token in (
        create_refresh_token(payload, expires_delta=timedelta(seconds=-1)),
        create_access_token(payload),
    ):
        response = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        assert response.status_code == 401


async def test_membership_removal_revokes_access_and_refresh(
    client, db_session, test_user, test_tenant
):
    payload = {"sub": str(test_user.id), "tenant_id": str(test_tenant.id), "role": "owner"}
    access, refresh = create_access_token(payload), create_refresh_token(payload)
    await db_session.execute(
        delete(Membership).where(
            Membership.user_id == test_user.id, Membership.tenant_id == test_tenant.id
        )
    )
    await db_session.commit()
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer " + access, "X-Tenant-ID": str(test_tenant.id)},
    )
    assert response.status_code in (401, 403)
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert response.status_code == 401


async def test_disabled_identity_cannot_refresh(client, db_session, test_user, test_tenant):
    token = create_refresh_token(
        {"sub": str(test_user.id), "tenant_id": str(test_tenant.id), "role": "owner"}
    )
    test_user.is_active = False
    await db_session.commit()
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 401


async def test_signed_role_claim_cannot_override_current_membership(
    client, db_session, test_user, test_tenant
):
    membership = await db_session.scalar(
        select(Membership).where(
            Membership.user_id == test_user.id, Membership.tenant_id == test_tenant.id
        )
    )
    membership.role = RoleEnum.VIEWER
    await db_session.commit()
    token = create_access_token(
        {"sub": str(test_user.id), "tenant_id": str(test_tenant.id), "role": "owner"}
    )
    headers = {"Authorization": "Bearer " + token, "X-Tenant-ID": str(test_tenant.id)}
    response = await client.post(
        "/api/v1/leads", headers=headers, json={"title": "Forged privilege"}
    )
    assert response.status_code == 403
    response = await client.get("/api/v1/auth/permissions", headers=headers)
    assert response.status_code == 200 and "leads:write" not in response.json()["permissions"]


async def test_logout_revokes_access_refresh_family_and_preserves_other_sessions(
    client, test_user, test_tenant
):
    first = await client.post(
        "/api/v1/auth/login", data={"username": test_user.email, "password": "password"}
    )
    second = await client.post(
        "/api/v1/auth/login", data={"username": test_user.email, "password": "password"}
    )
    assert first.status_code == second.status_code == 200
    tokens, other = first.json(), second.json()
    headers = {
        "Authorization": "Bearer " + tokens["access_token"],
        "X-Tenant-ID": str(test_tenant.id),
    }
    assert (
        decode_token(tokens["access_token"])["sid"] == decode_token(tokens["refresh_token"])["sid"]
    )
    response = await client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 401
    assert (
        await client.get(
            "/api/v1/auth/me",
            headers={**headers, "Authorization": "Bearer " + other["access_token"]},
        )
    ).status_code == 200


async def test_refresh_rotation_replay_revokes_the_whole_family(client, test_user, test_tenant):
    login = await client.post(
        "/api/v1/auth/login", data={"username": test_user.email, "password": "password"}
    )
    original = login.json()
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original["refresh_token"]}
    )
    assert refreshed.status_code == 200
    rotated = refreshed.json()
    assert rotated["refresh_token"] != original["refresh_token"]
    assert (
        decode_token(rotated["refresh_token"])["sid"]
        == decode_token(original["refresh_token"])["sid"]
    )
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original["refresh_token"]}
    )
    assert replay.status_code == 401
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    ).status_code == 401
    response = await client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": "Bearer " + rotated["access_token"],
            "X-Tenant-ID": str(test_tenant.id),
        },
    )
    assert response.status_code == 401


async def test_concurrent_refresh_claim_is_atomic_and_replay_revokes():
    import asyncio
    from app.core.token_sessions import consume_refresh, session_active, token_keys, redis_client

    payload = decode_token(create_refresh_token({"sub": str(uuid4()), "tenant_id": str(uuid4())}))
    claimed = await asyncio.gather(consume_refresh(payload), consume_refresh(payload))
    assert sorted(claimed) == [False, True]
    assert not await session_active(payload)
    client = redis_client()
    try:
        assert await client.get(token_keys(payload)[0]) == "revoked"
        assert await client.get(token_keys(payload)[1]) == "consumed"
        assert payload["sid"] not in "".join(token_keys(payload))
        await client.delete(*token_keys(payload))
    finally:
        await client.aclose()


async def test_redis_outage_fails_closed(client, test_user, test_tenant, monkeypatch):
    from redis.asyncio import Redis
    import app.core.token_sessions as sessions

    token = create_access_token({"sub": str(test_user.id), "tenant_id": str(test_tenant.id)})
    monkeypatch.setattr(
        sessions,
        "redis_client",
        lambda: Redis.from_url(
            "redis://127.0.0.1:1/0", socket_timeout=0.1, socket_connect_timeout=0.1
        ),
    )
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer " + token, "X-Tenant-ID": str(test_tenant.id)},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication state unavailable"}


async def test_disabled_tenant_cannot_refresh(client, db_session, test_user, test_tenant):
    token = create_refresh_token({"sub": str(test_user.id), "tenant_id": str(test_tenant.id)})
    test_tenant.is_active = False
    await db_session.commit()
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 401


async def test_unsubscribe_capability_and_auth_token_cannot_be_substituted(
    client, test_user, test_tenant, monkeypatch
):
    from urllib.parse import urlsplit, parse_qs
    from app.services.crm.unsubscribe import unsubscribe_url, decode_unsubscribe_token

    monkeypatch.setenv("CRM_PUBLIC_BASE_URL", "https://crm.example.com")
    capability = parse_qs(urlsplit(unsubscribe_url(test_tenant.id, uuid4())).query)["token"][0]
    assert decode_token(capability) is None
    assert decode_unsubscribe_token(capability)["type"] == "unsubscribe"
    assert (
        await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer " + capability, "X-Tenant-ID": str(test_tenant.id)},
        )
    ).status_code == 401
    for token in [
        create_access_token({"sub": str(test_user.id), "tenant_id": str(test_tenant.id)}),
        create_refresh_token({"sub": str(test_user.id), "tenant_id": str(test_tenant.id)}),
    ]:
        assert decode_unsubscribe_token(token) is None
        assert (
            await client.post("/api/v1/unsubscribe", params={"token": token})
        ).status_code == 400
