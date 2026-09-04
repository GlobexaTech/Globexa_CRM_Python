"""Redis client for Globexa CRM."""
from typing import Optional
import redis.asyncio as redis
from redis.asyncio import Redis

from app.core.config import get_settings

_redis_client: Optional[Redis] = None


async def get_redis() -> Redis:
    """Get or create the Redis client."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(
            settings.redis.url,
            max_connections=settings.redis.max_connections,
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    """Close the Redis client."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None