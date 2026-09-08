"""Atomic Redis rate limits shared by API replicas; Redis errors fail closed."""

import hashlib
from fastapi import HTTPException, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError
from app.core.config import get_settings
from app.core.security import decode_token

SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


async def check_rate(key, limit=120, seconds=60):
    client = Redis.from_url(
        get_settings().redis.url, socket_timeout=2, socket_connect_timeout=2
    )
    try:
        count = await client.eval(
            SCRIPT, 1, "crm:rate:" + hashlib.sha256(key.encode()).hexdigest(), seconds
        )
        if count > limit:
            raise HTTPException(
                429, "Rate limit exceeded", headers={"Retry-After": str(seconds)}
            )
    except RedisError:
        raise HTTPException(503, "Rate limit service unavailable") from None
    finally:
        await client.aclose()


async def enforce_rate(request: Request):
    if request.method not in {
        "POST",
        "PATCH",
        "PUT",
        "DELETE",
    } or not request.url.path.startswith("/api/v1/"):
        return
    auth = request.headers.get("Authorization", "")
    token = decode_token(auth[7:]) if auth.startswith("Bearer ") else None
    if token and token.get("type") == "access":
        await check_rate(f"user:{token.get('tenant_id')}:{token.get('sub')}")
    else:
        address = request.client.host if request.client else "unknown"
        await check_rate("ingress:" + address, 100)
