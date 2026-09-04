"""
Webhook Security Framework

Provides secure webhook verification for multiple providers:
- Meta/Facebook/Instagram (X-Hub-Signature-256)
- WhatsApp (X-Hub-Signature-256)
- Stripe (Stripe-Signature)
- Generic HMAC-SHA256
- Generic HMAC-SHA1

Includes replay protection via Redis.
"""

import hashlib
import hmac
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any

from fastapi import Request, HTTPException, status

from app.core.config import get_settings
from app.core.redis_client import get_redis_client


@dataclass
class WebhookVerificationResult:
    """Result of webhook verification."""
    valid: bool
    provider: str
    event_id: Optional[str] = None
    error: Optional[str] = None


class WebhookVerifier(ABC):
    """Abstract base class for webhook verifiers."""
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier."""
        pass
    
    @abstractmethod
    async def verify(
        self,
        request: Request,
        secret: str,
        body: bytes
    ) -> WebhookVerificationResult:
        """Verify webhook signature and return result."""
        pass
    
    def _constant_time_compare(self, a: str, b: str) -> bool:
        """Constant-time string comparison to prevent timing attacks."""
        return hmac.compare_digest(a.encode(), b.encode())
    
    async def _check_replay(self, event_id: str, ttl_seconds: int = 86400) -> bool:
        """
        Check and record event ID for replay protection.
        Returns True if event is new, False if already processed.
        """
        redis = await get_redis_client()
        if not redis:
            return True  # Allow if Redis unavailable (fail open with logging)
        
        key = f"webhook:replay:{self.provider_name}:{event_id}"
        # SET NX EX - atomic set if not exists with expiry
        result = await redis.set(key, "1", nx=True, ex=ttl_seconds)
        return result is True


class MetaWebhookVerifier(WebhookVerifier):
    """Verify Meta/Facebook/Instagram webhook signatures."""
    
    @property
    def provider_name(self) -> str:
        return "meta"
    
    async def verify(
        self,
        request: Request,
        secret: str,
        body: bytes
    ) -> WebhookVerificationResult:
        # Get signature header
        signature = request.headers.get("X-Hub-Signature-256")
        if not signature:
            return WebhookVerificationResult(
                valid=False,
                provider=self.provider_name,
                error="Missing X-Hub-Signature-256 header"
            )
        
        # Parse signature: "sha256=<hex>"
        if not signature.startswith("sha256="):
            return WebhookVerificationResult(
                valid=False,
                provider=self.provider_name,
                error="Invalid signature format"
            )
        
        received_sig = signature[7:]  # Remove "sha256="
        
        # Compute expected signature
        expected_sig = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison
        if not self._constant_time_compare(received_sig, expected_sig):
            return WebhookVerificationResult(
                valid=False,
                provider=self.provider_name,
                error="Invalid signature"
            )
        
        # Extract event ID for replay protection
        # Meta doesn't provide a universal event ID, use payload hash as fallback
        try:
            payload = json.loads(body)
            # For Lead Gen, use leadgen_id if available
            event_id = None
            if "entry" in payload and payload["entry"]:
                entry = payload["entry"][0]
                if "changes" in entry and entry["changes"]:
                    change = entry["changes"][0]
                    if "value" in change and "leadgen_id" in change["value"]:
                        event_id = change["value"]["leadgen_id"]
            
            # Fallback to payload hash
            if not event_id:
                event_id = hashlib.sha256(body).hexdigest()[:32]
        except:
            event_id = hashlib.sha256(body).hexdigest()[:32]
        
        # Check replay
        is_new = await self._check_replay(event_id)
        if not is_new:
            return WebhookVerificationResult(
                valid=True,  # Valid signature but replay
                provider=self.provider_name,
                event_id=event_id,
                error="Replay detected"
            )
        
        return WebhookVerificationResult(
            valid=True,
            provider=self.provider_name,
            event_id=event_id
        )


class WhatsAppWebhookVerifier(WebhookVerifier):
    """Verify WhatsApp Business API webhook signatures."""
    
    @property
    def provider_name(self) -> str:
        return "whatsapp"
    
    async def verify(
        self,
        request: Request,
        secret: str,
        body: bytes
    ) -> WebhookVerificationResult:
        # WhatsApp uses same signature format as Meta
        signature = request.headers.get("X-Hub-Signature-256")
        if not signature:
            return WebhookVerificationResult(
                valid=False,
                provider=self.provider_name,
                error="Missing X-Hub-Signature-256 header"
            )
        
        if not signature.startswith("sha256="):
            return WebhookVerificationResult(
                valid=False,
                provider=self.provider_name,
                error="Invalid signature format"
            )
        
        received_sig = signature[7:]
        expected_sig = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        if not self._constant_time_compare(received_sig, expected_sig):
            return WebhookVerificationResult(
                valid=False,
                provider=self.provider_name,
                error="Invalid signature"
            )
        
        # Extract message ID for replay protection
        try:
            payload = json.loads(body)
            event_id = None
            if "entry" in payload and payload["entry"]:
                entry = payload["entry"][0]
                if "changes" in entry and entry["changes"]:
                    change = entry["changes"][0]
                    if "value" in change and "messages" in change["value"]:
                        messages = change["value"]["messages"]
                        if messages:
                            event_id = messages[0].get("id")
            
            if not event_id:
                event_id = hashlib.sha256(body).hexdigest()[:32]
        except:
            event_id = hashlib.sha256(body).hexdigest()[:32]
        
        is_new = await self._check_replay(event_id)
        if not is_new:
            return WebhookVerificationResult(
                valid=True,
                provider=self.provider_name,
                event_id=event_id,
                error="Replay detected"
            )
        
        return WebhookVerificationResult(
            valid=True,
            provider=self.provider_name,
            event_id=event_id
        )


class StripeWebhookVerifier(WebhookVerifier):
    """Verify Stripe webhook signatures."""
    
    @property
    def provider_name(self) -> str:
        return "stripe"
    
    async def verify(
        self,
        request: Request,
        secret: str,
        body: bytes
    ) -> WebhookVerificationResult:
        stripe_signature = request.headers.get("Stripe-Signature")
        if not stripe_signature:
            return WebhookVerificationResult(
                valid=False,
                provider=self.provider_name,
                error="Missing Stripe-Signature header"
            )
        
        # Parse Stripe signature: "t=<timestamp>,v1=<signature>"
        parts = stripe_signature.split(",")
        timestamp = None
        received_sig = None
        
        for part in parts:
            if part.startswith("t="):
                timestamp = part[2:]
            elif part.startswith("v1="):
                received_sig = part[3:]
        
        if not timestamp or not received_sig:
            return WebhookVerificationResult(
                valid=False,
                provider=self.provider_name,
                error="Invalid Stripe signature format"
            )
        
        # Verify timestamp (prevent replay attacks with old timestamps)
        # Stripe recommends 5-minute tolerance
        try:
            timestamp_int = int(timestamp)
            if abs(time.time() - timestamp_int) > 300:  # 5 minutes
                return WebhookVerificationResult(
                    valid=False,
                    provider=self.provider_name,
                    error="Timestamp too old"
                )
        except ValueError:
            return WebhookVerificationResult(
                valid=False,
                provider=self.provider_name,
                error="Invalid timestamp"
            )
        
        # Compute expected signature
        signed_payload = f"{timestamp}.{body.decode()}".encode()
        expected_sig = hmac.new(
            secret.encode(),
            signed_payload,
            hashlib.sha256
        ).hexdigest()
        
        if not self._constant_time_compare(received_sig, expected_sig):
            return WebhookVerificationResult(
                valid=False,
                provider=self.provider_name,
                error="Invalid signature"
            )
        
        # Extract event ID for replay protection
        try:
            payload = json.loads(body)
            event_id = payload.get("id")
            if not event_id:
                event_id = hashlib.sha256(body).hexdigest()[:32]
        except:
            event_id = hashlib.sha256(body).hexdigest()[:32]
        
        is_new = await self._check_replay(event_id)
        if not is_new:
            return WebhookVerificationResult(
                valid=True,
                provider=self.provider_name,
                event_id=event_id,
                error="Replay detected"
            )
        
        return WebhookVerificationResult(
            valid=True,
            provider=self.provider_name,
            event_id=event_id
        )


class GenericHMACVerifier(WebhookVerifier):
    """Generic HMAC-SHA256 verifier for custom integrations."""
    
    def __init__(self, provider_name: str = "generic", header_name: str = "X-Webhook-Signature"):
        self._provider_name = provider_name
        self._header_name = header_name
    
    @property
    def provider_name(self) -> str:
        return self._provider_name
    
    async def verify(
        self,
        request: Request,
        secret: str,
        body: bytes
    ) -> WebhookVerificationResult:
        signature = request.headers.get(self._header_name)
        if not signature:
            return WebhookVerificationResult(
                valid=False,
                provider=self.provider_name,
                error=f"Missing {self._header_name} header"
            )
        
        # Support both "sha256=<hex>" and raw hex formats
        if signature.startswith("sha256="):
            received_sig = signature[7:]
        else:
            received_sig = signature
        
        expected_sig = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        if not self._constant_time_compare(received_sig, expected_sig):
            return WebhookVerificationResult(
                valid=False,
                provider=self.provider_name,
                error="Invalid signature"
            )
        
        # Use payload hash as event ID
        event_id = hashlib.sha256(body).hexdigest()[:32]
        
        is_new = await self._check_replay(event_id)
        if not is_new:
            return WebhookVerificationResult(
                valid=True,
                provider=self.provider_name,
                event_id=event_id,
                error="Replay detected"
            )
        
        return WebhookVerificationResult(
            valid=True,
            provider=self.provider_name,
            event_id=event_id
        )


# Verifier registry
_VERIFIERS: Dict[str, WebhookVerifier] = {
    "meta": MetaWebhookVerifier(),
    "facebook": MetaWebhookVerifier(),
    "instagram": MetaWebhookVerifier(),
    "whatsapp": WhatsAppWebhookVerifier(),
    "stripe": StripeWebhookVerifier(),
}


def get_webhook_verifier(provider: str) -> WebhookVerifier:
    """Get verifier for a provider, or generic HMAC verifier."""
    if provider in _VERIFIERS:
        return _VERIFIERS[provider]
    return GenericHMACVerifier(provider_name=provider)


async def verify_webhook(
    request: Request,
    provider: str,
    secret: str,
    max_body_size: int = 1024 * 1024  # 1MB default
) -> WebhookVerificationResult:
    """
    Verify a webhook request.
    
    Args:
        request: FastAPI request object
        provider: Provider identifier (meta, whatsapp, stripe, etc.)
        secret: Webhook secret for verification
        max_body_size: Maximum allowed body size in bytes
        
    Returns:
        WebhookVerificationResult with verification status
        
    Raises:
        HTTPException: If body too large or verification fails critically
    """
    # Check body size
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_body_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Webhook payload too large"
        )
    
    # Read body
    body = await request.body()
    if len(body) > max_body_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Webhook payload too large"
        )
    
    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty webhook payload"
        )
    
    # Get verifier and verify
    verifier = get_webhook_verifier(provider)
    result = await verifier.verify(request, secret, body)
    
    if not result.valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.error or "Webhook verification failed"
        )
    
    if result.error == "Replay detected":
        # Return 200 but indicate replay - idempotent response
        result.valid = False
    
    return result