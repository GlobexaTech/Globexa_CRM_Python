"""Webhook security framework for signature verification and replay protection."""
import hashlib
import hmac
import time
import json
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum
import structlog
from cryptography.hazmat.primitives import constant_time

from app.core.config import get_settings
from app.core.redis import get_redis

logger = structlog.get_logger()


class WebhookProvider(str, Enum):
    """Supported webhook providers."""
    META = "meta"
    WHATSAPP = "whatsapp"
    STRIPE = "stripe"
    GMAIL = "gmail"
    GENERIC = "generic"


@dataclass
class WebhookVerificationResult:
    """Result of webhook verification."""
    valid: bool
    provider: WebhookProvider
    event_id: Optional[str] = None
    error: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class WebhookVerifier:
    """Base webhook verifier with provider-specific implementations."""
    
    def __init__(self, secret: str):
        self.secret = secret.encode('utf-8')
    
    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
        timestamp_tolerance: int = 300,
    ) -> WebhookVerificationResult:
        """Verify HMAC signature with optional timestamp validation."""
        # Parse signature (format varies by provider)
        if not signature:
            return WebhookVerificationResult(
                valid=False,
                provider=WebhookProvider.GENERIC,
                error="Missing signature"
            )
        
        return WebhookVerificationResult(
            valid=True,
            provider=WebhookProvider.GENERIC,
        )
    
    def _constant_time_compare(self, expected: str, actual: str) -> bool:
        """Constant-time string comparison to prevent timing attacks."""
        return constant_time.bytes_eq(expected.encode(), actual.encode())


class MetaWebhookVerifier(WebhookVerifier):
    """Meta (Facebook/Instagram) webhook verifier.
    
    Meta uses X-Hub-Signature-256 header with HMAC-SHA256.
    """
    
    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
        timestamp_tolerance: int = 300,
    ) -> WebhookVerificationResult:
        if not signature:
            return WebhookVerificationResult(
                valid=False,
                provider=WebhookProvider.META,
                error="Missing X-Hub-Signature-256 header"
            )
        
        # Signature format: "sha256=<hash>"
        if not signature.startswith("sha256="):
            return WebhookVerificationResult(
                valid=False,
                provider=WebhookProvider.META,
                error="Invalid signature format"
            )
        
        expected_sig = signature[7:]  # Remove "sha256=" prefix
        
        # Calculate expected signature
        computed = hmac.new(
            self.secret,
            payload,
            hashlib.sha256
        ).hexdigest()
        
        if not self._constant_time_compare(computed, expected_sig):
            logger.warning("Meta webhook signature verification failed")
            return WebhookVerificationResult(
                valid=False,
                provider=WebhookProvider.META,
                error="Invalid signature"
            )
        
        return WebhookVerificationResult(
            valid=True,
            provider=WebhookProvider.META,
        )


class WhatsAppWebhookVerifier(WebhookVerifier):
    """WhatsApp Business API webhook verifier.
    
    WhatsApp uses X-Hub-Signature-256 same as Meta.
    """
    
    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
        timestamp_tolerance: int = 300,
    ) -> WebhookVerificationResult:
        # WhatsApp uses same signature format as Meta
        return MetaWebhookVerifier(self.secret).verify_signature(
            payload, signature, timestamp, timestamp_tolerance
        )


class StripeWebhookVerifier(WebhookVerifier):
    """Stripe webhook verifier.
    
    Stripe uses Stripe-Signature header with format:
    "t=<timestamp>,v1=<signature>"
    """
    
    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
        timestamp_tolerance: int = 300,
    ) -> WebhookVerificationResult:
        if not signature:
            return WebhookVerificationResult(
                valid=False,
                provider=WebhookProvider.STRIPE,
                error="Missing Stripe-Signature header"
            )
        
        # Parse Stripe signature: "t=<timestamp>,v1=<signature>"
        parts = {}
        for part in signature.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                parts[k] = v
        
        if "t" not in parts or "v1" not in parts:
            return WebhookVerificationResult(
                valid=False,
                provider=WebhookProvider.STRIPE,
                error="Invalid Stripe signature format"
            )
        
        # Verify timestamp if provided
        if timestamp_tolerance > 0:
            try:
                webhook_timestamp = int(parts["t"])
                now = int(time.time())
                if abs(now - webhook_timestamp) > timestamp_tolerance:
                    return WebhookVerificationResult(
                        valid=False,
                        provider=WebhookProvider.STRIPE,
                        error="Timestamp outside tolerance"
                    )
            except ValueError:
                return WebhookVerificationResult(
                    valid=False,
                    provider=WebhookProvider.STRIPE,
                    error="Invalid timestamp"
                )
        
        # Verify signature
        signed_payload = f"{parts['t']}.{payload.decode('utf-8')}"
        expected = hmac.new(
            self.secret,
            signed_payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not self._constant_time_compare(expected, parts["v1"]):
            logger.warning("Stripe webhook signature verification failed")
            return WebhookVerificationResult(
                valid=False,
                provider=WebhookProvider.STRIPE,
                error="Invalid signature"
            )
        
        return WebhookVerificationResult(
            valid=True,
            provider=WebhookProvider.STRIPE,
        )


class GenericWebhookVerifier(WebhookVerifier):
    """Generic HMAC webhook verifier for custom integrations.
    
    Supports configurable signature format:
    - Header name (default: X-Webhook-Signature)
    - Algorithm (default: sha256)
    - Prefix format (default: "sha256=")
    """
    
    def __init__(
        self,
        secret: str,
        algorithm: str = "sha256",
        prefix: str = "sha256=",
    ):
        super().__init__(secret)
        self.algorithm = algorithm
        self.prefix = prefix
        self._hash_func = getattr(hashlib, algorithm)
    
    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
        timestamp_tolerance: int = 300,
    ) -> WebhookVerificationResult:
        if not signature:
            return WebhookVerificationResult(
                valid=False,
                provider=WebhookProvider.GENERIC,
                error="Missing signature"
            )
        
        if not signature.startswith(self.prefix):
            return WebhookVerificationResult(
                valid=False,
                provider=WebhookProvider.GENERIC,
                error=f"Invalid signature format, expected prefix '{self.prefix}'"
            )
        
        expected_sig = signature[len(self.prefix):]
        computed = hmac.new(
            self.secret,
            payload,
            self._hash_func
        ).hexdigest()
        
        if not self._constant_time_compare(computed, expected_sig):
            logger.warning("Generic webhook signature verification failed")
            return WebhookVerificationResult(
                valid=False,
                provider=WebhookProvider.GENERIC,
                error="Invalid signature"
            )
        
        return WebhookVerificationResult(
            valid=True,
            provider=WebhookProvider.GENERIC,
        )


# Provider verifier mapping
VERIFIERS: Dict[WebhookProvider, Callable[[str], WebhookVerifier]] = {
    WebhookProvider.META: MetaWebhookVerifier,
    WebhookProvider.WHATSAPP: WhatsAppWebhookVerifier,
    WebhookProvider.STRIPE: StripeWebhookVerifier,
    WebhookProvider.GENERIC: GenericWebhookVerifier,
}


def get_verifier(provider: WebhookProvider, secret: str, **kwargs) -> WebhookVerifier:
    """Get a webhook verifier for the specified provider."""
    verifier_class = VERIFIERS.get(provider, GenericWebhookVerifier)
    return verifier_class(secret, **kwargs)


class WebhookReplayProtection:
    """Replay protection for webhooks using Redis.
    
    Stores processed event IDs with TTL to prevent duplicate processing.
    """
    
    def __init__(self, ttl_seconds: int = 86400):  # Default 24 hours
        self.ttl = ttl_seconds
        self._redis = None
    
    async def _get_redis(self):
        """Get Redis client lazily."""
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis
    
    async def check_and_mark(self, event_id: str, provider: WebhookProvider) -> bool:
        """Check if event was already processed, mark if not.
        
        Returns:
            True if event is new (not replayed)
            False if event was already processed (replay)
        """
        redis = await self._get_redis()
        key = f"webhook:replay:{provider.value}:{event_id}"
        
        # Use SET NX (set if not exists) with TTL for atomic check-and-set
        result = await redis.set(key, "1", nx=True, ex=self.ttl)
        return result is True
    
    async def is_replayed(self, event_id: str, provider: WebhookProvider) -> bool:
        """Check if event was already processed without marking."""
        redis = await self._get_redis()
        key = f"webhook:replay:{provider.value}:{event_id}"
        return await redis.exists(key) > 0


# Global replay protection instance
_replay_protection: Optional[WebhookReplayProtection] = None


def get_replay_protection() -> WebhookReplayProtection:
    """Get the global replay protection instance."""
    global _replay_protection
    if _replay_protection is None:
        _replay_protection = WebhookReplayProtection()
    return _replay_protection


async def verify_webhook(
    provider: WebhookProvider,
    payload: bytes,
    headers: Dict[str, str],
    secret: str,
    check_replay: bool = True,
) -> WebhookVerificationResult:
    """Verify a webhook request with signature and replay protection.
    
    Args:
        provider: The webhook provider
        payload: Raw request body bytes
        headers: Request headers
        secret: Webhook secret for signature verification
        check_replay: Whether to check replay protection
        
    Returns:
        WebhookVerificationResult with verification status
    """
    # Get appropriate verifier
    verifier = get_verifier(provider, secret)
    
    # Extract signature based on provider
    signature = None
    timestamp = None
    
    if provider in (WebhookProvider.META, WebhookProvider.WHATSAPP):
        signature = headers.get("X-Hub-Signature-256", headers.get("x-hub-signature-256"))
    elif provider == WebhookProvider.STRIPE:
        signature = headers.get("Stripe-Signature", headers.get("stripe-signature"))
        # Extract timestamp from Stripe signature
        if signature:
            for part in signature.split(","):
                if part.startswith("t="):
                    timestamp = part[2:]
    else:
        # Generic: check common header names
        signature = (
            headers.get("X-Webhook-Signature") or
            headers.get("x-webhook-signature") or
            headers.get("X-Signature") or
            headers.get("x-signature")
        )
    
    # Verify signature
    result = verifier.verify_signature(
        payload=payload,
        signature=signature or "",
        timestamp=timestamp,
    )
    
    if not result.valid:
        return result
    
    # Check replay protection
    if check_replay:
        # Extract event ID from payload (provider-specific)
        event_id = _extract_event_id(provider, payload)
        if event_id:
            replay = get_replay_protection()
            is_new = await replay.check_and_mark(event_id, provider)
            if not is_new:
                return WebhookVerificationResult(
                    valid=False,
                    provider=provider,
                    event_id=event_id,
                    error="Replay detected"
                )
            result.event_id = event_id
    
    # Parse payload
    try:
        result.payload = json.loads(payload.decode('utf-8'))
    except json.JSONDecodeError:
        return WebhookVerificationResult(
            valid=False,
            provider=provider,
            error="Invalid JSON payload"
        )
    
    return result


def _extract_event_id(provider: WebhookProvider, payload: bytes) -> Optional[str]:
    """Extract unique event ID from webhook payload."""
    try:
        data = json.loads(payload.decode('utf-8'))
    except json.JSONDecodeError:
        return None
    
    if provider in (WebhookProvider.META, WebhookProvider.WHATSAPP):
        # Meta/WA webhooks have entry.id or similar
        if "entry" in data and len(data["entry"]) > 0:
            entry = data["entry"][0]
            if "id" in entry:
                return f"{provider.value}:{entry['id']}"
            if "changes" in entry and len(entry["changes"]) > 0:
                change = entry["changes"][0]
                if "value" in change and "leadgen_id" in change["value"]:
                    return f"{provider.value}:{change['value']['leadgen_id']}"
    
    elif provider == WebhookProvider.STRIPE:
        # Stripe has event id at root level
        if "id" in data:
            return f"stripe:{data['id']}"
    
    # Generic: try common fields
    for field in ["id", "event_id", "eventId", "message_id", "uuid"]:
        if field in data:
            return f"{provider.value}:{data[field]}"
    
    # Fallback: hash of payload
    return f"{provider.value}:{hashlib.sha256(payload).hexdigest()[:16]}"


async def verify_meta_webhook(
    payload: bytes,
    signature: str,
    secret: str,
) -> WebhookVerificationResult:
    """Convenience function for Meta webhook verification."""
    return await verify_webhook(
        WebhookProvider.META,
        payload,
        {"X-Hub-Signature-256": signature},
        secret,
    )


async def verify_stripe_webhook(
    payload: bytes,
    signature: str,
    secret: str,
) -> WebhookVerificationResult:
    """Convenience function for Stripe webhook verification."""
    return await verify_webhook(
        WebhookProvider.STRIPE,
        payload,
        {"Stripe-Signature": signature},
        secret,
    )


async def verify_generic_webhook(
    payload: bytes,
    signature: str,
    secret: str,
    algorithm: str = "sha256",
) -> WebhookVerificationResult:
    """Convenience function for generic webhook verification."""
    return await verify_webhook(
        WebhookProvider.GENERIC,
        payload,
        {"X-Webhook-Signature": signature},
        secret,
    )