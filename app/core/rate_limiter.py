"""Rate limiting middleware using Redis."""
import time
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog

from app.core.redis import get_redis
from app.core.config import get_settings

logger = structlog.get_logger()


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit rule."""
    requests: int  # Max requests allowed
    window_seconds: int  # Time window in seconds
    key_prefix: str  # Redis key prefix
    scope: str  # "ip", "user", "tenant", "endpoint"
    endpoints: list[str]  # Endpoint patterns to apply to
    methods: list[str] = None  # HTTP methods to apply to (None = all)
    
    def __post_init__(self):
        if self.methods is None:
            self.methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]


class RateLimiter:
    """Redis-backed rate limiter with multiple scopes."""
    
    def __init__(self):
        self._redis = None
        self.configs: list[RateLimitConfig] = []
        self._initialized = False
        self._redis_available = False
    
    async def _get_redis(self):
        if self._redis is None:
            try:
                self._redis = await get_redis()
                # Test connection
                await self._redis.ping()
                self._redis_available = True
            except Exception as e:
                logger.warning("Redis not available for rate limiting", error=str(e))
                self._redis_available = False
                self._redis = None
        return self._redis
    
    def add_config(self, config: RateLimitConfig) -> None:
        """Add a rate limit configuration."""
        self.configs.append(config)
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check for forwarded headers (behind proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _get_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request (if authenticated)."""
        # This would be set by auth middleware
        return getattr(request.state, "user_id", None)
    
    def _get_tenant_id(self, request: Request) -> Optional[str]:
        """Extract tenant ID from request."""
        # This would be set by tenant middleware
        return getattr(request.state, "tenant_id", None)
    
    def _build_key(self, config: RateLimitConfig, request: Request) -> str:
        """Build Redis key based on scope."""
        if config.scope == "ip":
            identifier = self._get_client_ip(request)
        elif config.scope == "user":
            identifier = self._get_user_id(request) or self._get_client_ip(request)
        elif config.scope == "tenant":
            identifier = self._get_tenant_id(request) or self._get_client_ip(request)
        elif config.scope == "endpoint":
            identifier = f"{request.method}:{request.url.path}"
        else:
            identifier = self._get_client_ip(request)
        
        return f"ratelimit:{config.key_prefix}:{identifier}"
    
    def _matches_endpoint(self, config: RateLimitConfig, request: Request) -> bool:
        """Check if request matches the endpoint patterns."""
        path = request.url.path
        
        for pattern in config.endpoints:
            if pattern.endswith("*"):
                if path.startswith(pattern[:-1]):
                    return True
            elif path == pattern:
                return True
        
        return False
    
    async def check_rate_limit(self, request: Request) -> Optional[dict]:
        """Check if request is within rate limits.
        
        Returns:
            None if within limits, dict with rate limit info if exceeded
        """
        # If Redis is not available, skip rate limiting
        if not self._redis_available:
            redis = await self._get_redis()
            if not self._redis_available:
                return None
        
        redis = await self._get_redis()
        if not redis:
            return None
            
        now = int(time.time())
        
        for config in self.configs:
            # Check if this config applies to the request
            if not self._matches_endpoint(config, request):
                continue
            
            if request.method not in config.methods:
                continue
            
            key = self._build_key(config, request)
            window_start = now - config.window_seconds
            
            # Use sorted set for sliding window
            # Remove expired entries
            try:
                await redis.zremrangebyscore(key, 0, window_start)
                
                # Count current requests in window
                current_count = await redis.zcard(key)
                
                if current_count >= config.requests:
                    # Get oldest entry to calculate reset time
                    oldest = await redis.zrange(key, 0, 0, withscores=True)
                    reset_time = int(oldest[0][1]) + config.window_seconds if oldest else now + config.window_seconds
                    
                    return {
                        "limit": config.requests,
                        "remaining": 0,
                        "reset": reset_time,
                        "window": config.window_seconds,
                        "scope": config.scope,
                    }
                
                # Add current request
                await redis.zadd(key, {f"{now}:{time.time()}": now})
                await redis.expire(key, config.window_seconds + 1)
            except Exception as e:
                logger.warning("Rate limiter Redis error, skipping", error=str(e))
                return None
        
        return None
    
    async def get_limit_info(self, request: Request) -> dict:
        """Get current rate limit info for response headers."""
        if not self._redis_available:
            redis = await self._get_redis()
            if not self._redis_available:
                return {"limit": 0, "remaining": 0, "reset": 0}
        
        redis = await self._get_redis()
        if not redis:
            return {"limit": 0, "remaining": 0, "reset": 0}
            
        now = int(time.time())
        
        # Return info for the most restrictive matching config
        for config in self.configs:
            if not self._matches_endpoint(config, request):
                continue
            if request.method not in config.methods:
                continue
            
            key = self._build_key(config, request)
            window_start = now - config.window_seconds
            
            try:
                await redis.zremrangebyscore(key, 0, window_start)
                current_count = await redis.zcard(key)
                
                return {
                    "limit": config.requests,
                    "remaining": max(0, config.requests - current_count),
                    "reset": now + config.window_seconds,
                }
            except Exception as e:
                logger.warning("Rate limiter Redis error in get_limit_info", error=str(e))
                return {"limit": 0, "remaining": 0, "reset": 0}
        
        return {"limit": 0, "remaining": 0, "reset": 0}


# Default rate limit configurations
DEFAULT_RATE_LIMITS = [
    # Auth endpoints - strict limits
    RateLimitConfig(
        requests=5,
        window_seconds=300,  # 5 minutes
        key_prefix="auth",
        scope="ip",
        endpoints=["/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/password"],
        methods=["POST"],
    ),
    # AI endpoints - moderate limits
    RateLimitConfig(
        requests=30,
        window_seconds=60,
        key_prefix="ai",
        scope="user",
        endpoints=["/api/v1/ai/*"],
        methods=["POST"],
    ),
    # Lead crawler/miner - strict limits
    RateLimitConfig(
        requests=10,
        window_seconds=60,
        key_prefix="crawler",
        scope="tenant",
        endpoints=["/api/v1/leads/crawl", "/api/v1/leads/enrich"],
        methods=["POST"],
    ),
    # Campaign operations
    RateLimitConfig(
        requests=20,
        window_seconds=60,
        key_prefix="campaigns",
        scope="tenant",
        endpoints=["/api/v1/campaigns/*/send", "/api/v1/campaigns/*/launch"],
        methods=["POST"],
    ),
    # Integration management
    RateLimitConfig(
        requests=30,
        window_seconds=60,
        key_prefix="integrations",
        scope="tenant",
        endpoints=["/api/v1/integrations/*"],
        methods=["POST", "PUT", "PATCH", "DELETE"],
    ),
    # Expensive search endpoints
    RateLimitConfig(
        requests=60,
        window_seconds=60,
        key_prefix="search",
        scope="user",
        endpoints=["/api/v1/*/search", "/api/v1/*/filter"],
        methods=["GET", "POST"],
    ),
    # Bulk actions
    RateLimitConfig(
        requests=5,
        window_seconds=300,
        key_prefix="bulk",
        scope="tenant",
        endpoints=["/api/v1/*/bulk", "/api/v1/*/batch"],
        methods=["POST"],
    ),
    # General API - generous but present
    RateLimitConfig(
        requests=200,
        window_seconds=60,
        key_prefix="api",
        scope="user",
        endpoints=["/api/v1/*"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    ),
]


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
        for config in DEFAULT_RATE_LIMITS:
            _rate_limiter.add_config(config)
    return _rate_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""
    
    def __init__(self, app: ASGIApp, rate_limiter: Optional[RateLimiter] = None):
        super().__init__(app)
        self.rate_limiter = rate_limiter or get_rate_limiter()
    
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/healthz", "/ready", "/"]:
            return await call_next(request)
        
        # Check rate limit
        limit_info = await self.rate_limiter.check_rate_limit(request)
        
        if limit_info:
            # Rate limit exceeded
            logger.warning(
                "Rate limit exceeded",
                path=request.url.path,
                method=request.method,
                client_ip=self.rate_limiter._get_client_ip(request),
                limit=limit_info["limit"],
                scope=limit_info["scope"],
            )
            
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": limit_info["limit"],
                    "window_seconds": limit_info["window"],
                    "retry_after": max(1, limit_info["reset"] - int(time.time())),
                },
                headers={
                    "X-RateLimit-Limit": str(limit_info["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(limit_info["reset"]),
                    "Retry-After": str(max(1, limit_info["reset"] - int(time.time()))),
                }
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers to response
        info = await self.rate_limiter.get_limit_info(request)
        if info["limit"] > 0:
            response.headers["X-RateLimit-Limit"] = str(info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(info["reset"])
        
        return response