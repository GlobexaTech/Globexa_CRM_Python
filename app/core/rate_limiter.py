"""
Rate Limiting for Globexa CRM

Redis-backed rate limiting with support for:
- IP-level limits (unauthenticated)
- User-level limits
- Tenant-level limits
- Endpoint-specific limits
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List, Tuple

import redis.asyncio as redis
from fastapi import Request, HTTPException, status

from app.core.config import get_settings
from app.core.redis_client import get_redis


class RateLimitScope(str, Enum):
    """Rate limit scope types."""
    IP = "ip"
    USER = "user"
    TENANT = "tenant"
    ENDPOINT = "endpoint"


@dataclass
class RateLimitRule:
    """Rate limit rule configuration."""
    scope: RateLimitScope
    max_requests: int
    window_seconds: int
    # Path patterns this rule applies to (supports wildcards)
    paths: List[str]
    # Methods this rule applies to (empty = all)
    methods: List[str]


@dataclass
class RateLimitInfo:
    """Rate limit information for response headers."""
    limit: int
    remaining: int
    reset_seconds: int
    scope: RateLimitScope
    identifier: str


class RateLimiter:
    """
    Redis-backed rate limiter with multiple scopes.
    
    Uses sliding window log algorithm with Redis sorted sets for accuracy.
    """
    
    def __init__(self):
        self._rules: List[RateLimitRule] = []
        self._default_rules()
    
    def _default_rules(self) -> None:
        """Configure default rate limit rules."""
        # Login/registration - strict IP limits
        self.add_rule(RateLimitRule(
            scope=RateLimitScope.IP,
            max_requests=5,
            window_seconds=300,  # 5 minutes
            paths=["/api/v1/auth/login", "/api/v1/auth/register"],
            methods=["POST"]
        ))
        
        # Password/security endpoints
        self.add_rule(RateLimitRule(
            scope=RateLimitScope.IP,
            max_requests=10,
            window_seconds=3600,  # 1 hour
            paths=["/api/v1/auth/password/*", "/api/v1/auth/security/*"],
            methods=["POST", "PUT"]
        ))
        
        # AI endpoints - user level
        self.add_rule(RateLimitRule(
            scope=RateLimitScope.USER,
            max_requests=100,
            window_seconds=3600,  # 1 hour
            paths=["/api/v1/ai/*"],
            methods=["POST"]
        ))
        
        # Lead crawler/miner - tenant level
        self.add_rule(RateLimitRule(
            scope=RateLimitScope.TENANT,
            max_requests=50,
            window_seconds=3600,  # 1 hour
            paths=["/api/v1/leads/crawl", "/api/v1/leads/mine"],
            methods=["POST"]
        ))
        
        # Campaign sending - tenant level
        self.add_rule(RateLimitRule(
            scope=RateLimitScope.TENANT,
            max_requests=100,
            window_seconds=3600,  # 1 hour
            paths=["/api/v1/campaigns/*/send", "/api/v1/campaigns/*/schedule"],
            methods=["POST"]
        ))
        
        # Integration management - tenant level
        self.add_rule(RateLimitRule(
            scope=RateLimitScope.TENANT,
            max_requests=200,
            window_seconds=3600,
            paths=["/api/v1/integrations/*"],
            methods=["POST", "PUT", "DELETE"]
        ))
        
        # Bulk operations - tenant level
        self.add_rule(RateLimitRule(
            scope=RateLimitScope.TENANT,
            max_requests=20,
            window_seconds=3600,
            paths=["/api/v1/*/bulk*", "/api/v1/*/import", "/api/v1/*/export"],
            methods=["POST"]
        ))
        
        # Expensive search endpoints - user level
        self.add_rule(RateLimitRule(
            scope=RateLimitScope.USER,
            max_requests=60,
            window_seconds=60,  # 1 minute
            paths=["/api/v1/*/search"],
            methods=["GET", "POST"]
        ))
        
        # Public webhook endpoints - IP level (lenient)
        self.add_rule(RateLimitRule(
            scope=RateLimitScope.IP,
            max_requests=1000,
            window_seconds=60,
            paths=["/api/v1/webhooks/*"],
            methods=["POST"]
        ))
        
        # Default fallback - per IP generous limit
        self.add_rule(RateLimitRule(
            scope=RateLimitScope.IP,
            max_requests=1000,
            window_seconds=60,
            paths=["/*"],
            methods=[]
        ))
    
    def add_rule(self, rule: RateLimitRule) -> None:
        """Add a rate limit rule."""
        self._rules.append(rule)
        # Sort by specificity (fewer wildcards first)
        self._rules.sort(key=lambda r: sum(p.count("*") for p in r.paths))
    
    def _match_path(self, path: str, pattern: str) -> bool:
        """Check if path matches pattern with wildcards."""
        if pattern == "/*":
            return True
        if "*" not in pattern:
            return path == pattern
        
        # Simple wildcard matching
        import fnmatch
        return fnmatch.fnmatch(path, pattern)
    
    def _match_rule(self, request: Request, rule: RateLimitRule) -> bool:
        """Check if request matches a rule."""
        # Check path
        path_match = any(self._match_path(request.url.path, p) for p in rule.paths)
        if not path_match:
            return False
        
        # Check method
        if rule.methods and request.method not in rule.methods:
            return False
        
        return True
    
    def _get_identifier(self, request: Request, scope: RateLimitScope) -> Optional[str]:
        """Get identifier for the given scope."""
        if scope == RateLimitScope.IP:
            # Get real IP behind proxy
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
            return request.client.host if request.client else "unknown"
        
        elif scope == RateLimitScope.USER:
            # User ID from authenticated request state
            return getattr(request.state, "user_id", None)
        
        elif scope == RateLimitScope.TENANT:
            # Tenant ID from authenticated request state
            return getattr(request.state, "tenant_id", None)
        
        elif scope == RateLimitScope.ENDPOINT:
            return request.url.path
        
        return None
    
    async def check_rate_limit(
        self,
        request: Request,
        rule: RateLimitRule
    ) -> RateLimitInfo:
        """
        Check and consume rate limit for a request.
        
        Returns RateLimitInfo with current status.
        Raises HTTPException if limit exceeded.
        """
        redis_client = await get_redis()
        if not redis_client:
            # Fail open if Redis unavailable
            return RateLimitInfo(
                limit=rule.max_requests,
                remaining=rule.max_requests,
                reset_seconds=rule.window_seconds,
                scope=rule.scope,
                identifier="unknown"
            )
        
        identifier = self._get_identifier(request, rule.scope)
        if not identifier:
            # Cannot identify - fail open for user/tenant scopes
            # For IP scope, we should have an IP
            if rule.scope == RateLimitScope.IP:
                identifier = "unknown"
            else:
                return RateLimitInfo(
                    limit=rule.max_requests,
                    remaining=rule.max_requests,
                    reset_seconds=rule.window_seconds,
                    scope=rule.scope,
                    identifier="unidentified"
                )
        
        # Build Redis key
        key = f"ratelimit:{rule.scope.value}:{identifier}:{request.url.path}"
        
        now = time.time()
        window_start = now - rule.window_seconds
        
        # Use Redis sorted set for sliding window
        # Members are timestamps, scores are timestamps
        pipe = redis_client.pipeline()
        
        # Remove expired entries
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Count current requests
        pipe.zcard(key)
        
        # Add current request
        pipe.zadd(key, {str(now): now})
        
        # Set expiry on key
        pipe.expire(key, rule.window_seconds + 1)
        
        results = await pipe.execute()
        current_count = results[1]
        
        if current_count >= rule.max_requests:
            # Get oldest entry to calculate reset time
            oldest = await redis_client.zrange(key, 0, 0, withscores=True)
            if oldest:
                reset_time = int(oldest[0][1] + rule.window_seconds - now) + 1
            else:
                reset_time = rule.window_seconds
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {rule.scope.value}",
                headers={
                    "X-RateLimit-Limit": str(rule.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(reset_time),
                }
            )
        
        remaining = rule.max_requests - current_count - 1
        reset_seconds = rule.window_seconds
        
        return RateLimitInfo(
            limit=rule.max_requests,
            remaining=remaining,
            reset_seconds=reset_seconds,
            scope=rule.scope,
            identifier=identifier
        )
    
    async def check_request(self, request: Request) -> Optional[RateLimitInfo]:
        """
        Check all applicable rules for a request.
        
        Returns the most restrictive RateLimitInfo, or None if no rules match.
        Raises HTTPException if any limit is exceeded.
        """
        matched_rules = [r for r in self._rules if self._match_rule(request, r)]
        
        if not matched_rules:
            return None
        
        # Check all matching rules, use most restrictive result
        results = []
        for rule in matched_rules:
            info = await self.check_rate_limit(request, rule)
            results.append(info)
        
        # Return most restrictive (lowest remaining)
        return min(results, key=lambda r: r.remaining)


# Global rate limiter instance
rate_limiter = RateLimiter()


async def rate_limit_middleware(request: Request, call_next):
    """FastAPI middleware for rate limiting."""
    # Skip rate limiting for health checks
    if request.url.path in ["/health", "/health/live", "/health/ready"]:
        return await call_next(request)
    
    try:
        rate_info = await rate_limiter.check_request(request)
    except HTTPException:
        raise
    except Exception:
        # Fail open on unexpected errors
        rate_info = None
    
    response = await call_next(request)
    
    # Add rate limit headers if applicable
    if rate_info:
        response.headers["X-RateLimit-Limit"] = str(rate_info.limit)
        response.headers["X-RateLimit-Remaining"] = str(rate_info.remaining)
        response.headers["X-RateLimit-Reset"] = str(rate_info.reset_seconds)
    
    return response