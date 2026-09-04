"""
Security Headers Middleware

Adds security headers to all responses.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to responses."""
    
    def __init__(self, app, *, csp_policy: str = None, hsts_max_age: int = 31536000):
        super().__init__(app)
        self.csp_policy = csp_policy
        self.hsts_max_age = hsts_max_age
        self.settings = get_settings()
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # X-Content-Type-Options - prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Referrer-Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # X-Frame-Options - prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # Content-Security-Policy for API responses
        if self.csp_policy:
            response.headers["Content-Security-Policy"] = self.csp_policy
        else:
            # Restrictive CSP for APIs
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; "
                "frame-ancestors 'none'; "
                "base-uri 'none'; "
                "form-action 'none'"
            )
        
        # Strict-Transport-Security (HSTS) - only in production with HTTPS
        if self.settings.app.environment == "production":
            # Check if request is HTTPS or behind trusted proxy
            forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
            if forwarded_proto == "https" or request.url.scheme == "https":
                response.headers["Strict-Transport-Security"] = (
                    f"max-age={self.hsts_max_age}; includeSubDomains; preload"
                )
        
        # Permissions-Policy (formerly Feature-Policy)
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )
        
        # Cross-Origin-Opener-Policy
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        
        # Cross-Origin-Resource-Policy
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        
        return response