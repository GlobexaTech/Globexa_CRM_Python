"""Redis-backed session-family revocation and atomic single-use refresh rotation.

Only hashes of signed token identifiers are persisted. Redis must use durable
storage in deployment; its unavailability never permits token authentication.
"""

import hashlib
from datetime import datetime, timezone
from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError
from app.core.config import get_settings

ROTATE = """
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
if redis.call('EXISTS', KEYS[2]) == 1 then
  redis.call('SET', KEYS[1], 'revoked', 'EX', ARGV[1])
  return -1
end
redis.call('SET', KEYS[2], 'consumed', 'EX', ARGV[1])
return 1
"""


def token_keys(payload):
    family = hashlib.sha256(
        f"{payload['tenant_id']}:{payload['sub']}:{payload['sid']}".encode()
    ).hexdigest()
    token = hashlib.sha256(payload["jti"].encode()).hexdigest()
    prefix = "auth:v1:{" + family + "}:"
    return prefix + "revoked", prefix + "refresh:" + token


def redis_client():
    return Redis.from_url(
        get_settings().redis.url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
        max_connections=100,
    )


async def session_active(payload):
    client = redis_client()
    try:
        return not bool(await client.exists(token_keys(payload)[0]))
    except (RedisError, OSError):
        raise HTTPException(503, "Authentication state unavailable") from None
    finally:
        await client.aclose()


async def consume_refresh(payload):
    ttl = max(1, int(payload["session_exp"] - datetime.now(timezone.utc).timestamp()) + 1)
    client = redis_client()
    try:
        return int(await client.eval(ROTATE, 2, *token_keys(payload), ttl)) == 1
    except (RedisError, OSError):
        raise HTTPException(503, "Authentication state unavailable") from None
    finally:
        await client.aclose()


async def revoke_session(payload):
    ttl = max(1, int(payload["session_exp"] - datetime.now(timezone.utc).timestamp()) + 1)
    client = redis_client()
    try:
        await client.set(token_keys(payload)[0], "revoked", ex=ttl)
    except (RedisError, OSError):
        raise HTTPException(503, "Authentication state unavailable") from None
    finally:
        await client.aclose()
