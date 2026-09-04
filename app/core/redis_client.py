"""
Redis Client for Globexa CRM

Provides async Redis client for caching, rate limiting, webhook replay protection,
and other Redis-backed features.
"""

import redis.asyncio as redis
from typing import Optional

from app.core.config import get_settings


_redis_client: Optional[redis.Redis] = None


async def get_redis_client() -> Optional[redis.Redis]:
    """Get or create the global Redis client."""
    global _redis_client
    
    if _redis_client is not None:
        return _redis_client
    
    settings = get_settings()
    
    try:
        _redis_client = redis.from_url(
            settings.redis.url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.redis.max_connections,
        )
        # Test connection
        await _redis_client.ping()
        return _redis_client
    except Exception:
        # Return None if Redis unavailable - allow fail-open with logging
        _redis_client = None
        return None


async def close_redis_client() -> None:
    """Close the Redis client connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def get_redis() -> redis.Redis:
    """Get Redis client, raise if unavailable."""
    client = await get_redis_client()
    if client is None:
        raise RuntimeError("Redis client not available")
    return client