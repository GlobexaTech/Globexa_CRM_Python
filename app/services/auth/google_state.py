"""Single-use, browser-bound Google login state; secrets stay in Redis."""

import hashlib
import json
import secrets
from fastapi import HTTPException
from redis.exceptions import RedisError
from app.core.token_sessions import redis_client

COOKIE = "globexa_google_login"
TTL = 300
CONSUME = """
local value = redis.call('GET', KEYS[1])
if not value then return nil end
local item = cjson.decode(value)
if item.binding ~= ARGV[1] then return nil end
redis.call('DEL', KEYS[1])
return value
"""


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


async def begin():
    state, binding, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
    try:
        async with redis_client() as redis:
            await redis.set(
                "auth:google:" + digest(state),
                json.dumps(
                    {
                        "binding": digest(binding),
                        "nonce": nonce,
                        "verifier": verifier,
                    }
                ),
                ex=TTL,
                nx=True,
            )
    except RedisError:
        raise HTTPException(503, "Authentication state unavailable") from None
    return state, binding, nonce, verifier


async def consume(state, binding):
    if not state or not binding or len(state) > 128 or len(binding) > 128:
        raise ValueError("Invalid or expired Google login state")
    try:
        async with redis_client() as redis:
            value = await redis.eval(CONSUME, 1, "auth:google:" + digest(state), digest(binding))
    except RedisError:
        raise HTTPException(503, "Authentication state unavailable") from None
    if not value:
        raise ValueError("Invalid or expired Google login state")
    return json.loads(value)
