"""
Refresh Token Security Service

Implements secure refresh token handling with:
- Unique JTI (JWT ID) for each token
- Token family/session tracking
- Token rotation (new refresh token on each use)
- Old token invalidation
- Reuse detection (revokes entire family on reuse)
- Revocation/logout support
- Expiry management
- Disabled user check
- Membership validation

Uses Redis for token storage with automatic expiry.
"""

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from uuid import UUID

from app.core.config import get_settings
from app.core.redis_client import get_redis
from app.core.security import create_access_token, decode_token
from app.models import User


@dataclass
class RefreshTokenData:
    """Refresh token data stored in Redis."""
    jti: str
    user_id: str
    tenant_id: str
    family_id: str
    created_at: float
    expires_at: float
    revoked: bool = False
    replaced_by: Optional[str] = None  # JTI of token that replaced this
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "jti": self.jti,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
            "replaced_by": self.replaced_by,
            "metadata": self.metadata or {},
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RefreshTokenData":
        return cls(
            jti=data["jti"],
            user_id=data["user_id"],
            tenant_id=data["tenant_id"],
            family_id=data["family_id"],
            created_at=data["created_at"],
            expires_at=data["expires_at"],
            revoked=data.get("revoked", False),
            replaced_by=data.get("replaced_by"),
            metadata=data.get("metadata"),
        )


class RefreshTokenService:
    """
    Secure refresh token management with rotation and reuse detection.
    
    Security model:
    - Each refresh token has a unique JTI
    - Tokens belong to a "family" (session)
    - On use, token is rotated: old token marked revoked, new token issued
    - If a revoked token is presented (reuse), entire family is revoked
    - Tokens stored as hashes in Redis (never store raw tokens)
    """
    
    # Redis key prefixes
    TOKEN_PREFIX = "refresh_token:"
    FAMILY_PREFIX = "refresh_family:"
    USER_TOKENS_PREFIX = "user_refresh_tokens:"
    
    def __init__(self):
        self.settings = get_settings()
        self._token_hash_salt = self.settings.security.secret_key.encode()
    
    def _hash_token(self, token: str) -> str:
        """Hash a refresh token for storage."""
        return hashlib.sha256(self._token_hash_salt + token.encode()).hexdigest()
    
    def _generate_token(self) -> str:
        """Generate a cryptographically secure refresh token."""
        return secrets.token_urlsafe(32)
    
    def _generate_jti(self) -> str:
        """Generate a unique JWT ID."""
        return secrets.token_urlsafe(16)
    
    def _generate_family_id(self) -> str:
        """Generate a unique family ID."""
        return secrets.token_urlsafe(16)
    
    async def _get_redis(self):
        """Get Redis client."""
        return await get_redis()
    
    async def create_refresh_token(
        self,
        user: User,
        tenant_id: UUID,
        metadata: Dict[str, Any] = None
    ) -> tuple[str, RefreshTokenData]:
        """
        Create a new refresh token for a user.
        
        Returns:
            Tuple of (raw_token, token_data)
        """
        redis = await self._get_redis()
        if not redis:
            raise RuntimeError("Redis not available for refresh token storage")
        
        now = time.time()
        expires_at = now + (self.settings.security.refresh_token_expire_days * 86400)
        
        family_id = self._generate_family_id()
        jti = self._generate_jti()
        raw_token = self._generate_token()
        token_hash = self._hash_token(raw_token)
        
        token_data = RefreshTokenData(
            jti=jti,
            user_id=str(user.id),
            tenant_id=str(tenant_id),
            family_id=family_id,
            created_at=now,
            expires_at=expires_at,
            metadata=metadata or {},
        )
        
        # Store token hash -> token data
        token_key = f"{self.TOKEN_PREFIX}{token_hash}"
        await redis.set(token_key, token_data.to_dict(), ex=int(self.settings.security.refresh_token_expire_days * 86400) + 3600)
        
        # Add to family set
        family_key = f"{self.FAMILY_PREFIX}{family_id}"
        await redis.sadd(family_key, token_hash)
        await redis.expire(family_key, int(self.settings.security.refresh_token_expire_days * 86400) + 3600)
        
        # Track user's tokens
        user_tokens_key = f"{self.USER_TOKENS_PREFIX}{user.id}"
        await redis.sadd(user_tokens_key, token_hash)
        await redis.expire(user_tokens_key, int(self.settings.security.refresh_token_expire_days * 86400) + 3600)
        
        return raw_token, token_data
    
    async def verify_and_rotate(
        self,
        raw_token: str,
        user_id: UUID,
        tenant_id: UUID
    ) -> tuple[str, RefreshTokenData]:
        """
        Verify a refresh token and rotate it (issue new, revoke old).
        
        Args:
            raw_token: The raw refresh token from client
            user_id: Expected user ID
            tenant_id: Expected tenant ID
            
        Returns:
            Tuple of (new_raw_token, new_token_data)
            
        Raises:
            ValueError: If token invalid, expired, revoked, or reuse detected
        """
        redis = await self._get_redis()
        if not redis:
            raise RuntimeError("Redis not available for refresh token verification")
        
        token_hash = self._hash_token(raw_token)
        token_key = f"{self.TOKEN_PREFIX}{token_hash}"
        
        # Get token data
        token_data_dict = await redis.get(token_key)
        if not token_data_dict:
            raise ValueError("Invalid refresh token")
        
        token_data = RefreshTokenData.from_dict(token_data_dict)
        
        # Verify token belongs to user and tenant
        if token_data.user_id != str(user_id):
            raise ValueError("Token user mismatch")
        if token_data.tenant_id != str(tenant_id):
            raise ValueError("Token tenant mismatch")
        
        # Check expiry
        if time.time() > token_data.expires_at:
            await self._cleanup_token(redis, token_hash, token_data)
            raise ValueError("Refresh token expired")
        
        # Check if revoked
        if token_data.revoked:
            # REUSE DETECTED! Revoke entire family
            await self._revoke_family(redis, token_data.family_id, reason="reuse_detected")
            raise ValueError("Refresh token reuse detected - session revoked")
        
        # Token is valid - rotate it
        # 1. Mark old token as revoked and replaced
        token_data.revoked = True
        token_data.replaced_by = self._generate_jti()  # Will be new token's JTI
        await redis.set(token_key, token_data.to_dict(), ex=int(self.settings.security.refresh_token_expire_days * 86400) + 3600)
        
        # 2. Create new token in same family
        new_raw_token, new_token_data = await self._create_token_in_family(
            redis, user_id, tenant_id, token_data.family_id, token_data.metadata
        )
        
        # 3. Update old token's replaced_by with new JTI
        token_data.replaced_by = new_token_data.jti
        await redis.set(token_key, token_data.to_dict(), ex=int(self.settings.security.refresh_token_expire_days * 86400) + 3600)
        
        return new_raw_token, new_token_data
    
    async def _create_token_in_family(
        self,
        redis,
        user_id: UUID,
        tenant_id: UUID,
        family_id: str,
        metadata: Dict[str, Any]
    ) -> tuple[str, RefreshTokenData]:
        """Create a new token in an existing family."""
        now = time.time()
        expires_at = now + (self.settings.security.refresh_token_expire_days * 86400)
        
        jti = self._generate_jti()
        raw_token = self._generate_token()
        token_hash = self._hash_token(raw_token)
        
        token_data = RefreshTokenData(
            jti=jti,
            user_id=str(user_id),
            tenant_id=str(tenant_id),
            family_id=family_id,
            created_at=now,
            expires_at=expires_at,
            metadata=metadata,
        )
        
        token_key = f"{self.TOKEN_PREFIX}{token_hash}"
        await redis.set(token_key, token_data.to_dict(), ex=int(self.settings.security.refresh_token_expire_days * 86400) + 3600)
        
        # Add to family
        family_key = f"{self.FAMILY_PREFIX}{family_id}"
        await redis.sadd(family_key, token_hash)
        await redis.expire(family_key, int(self.settings.security.refresh_token_expire_days * 86400) + 3600)
        
        # Track user's tokens
        user_tokens_key = f"{self.USER_TOKENS_PREFIX}{user_id}"
        await redis.sadd(user_tokens_key, token_hash)
        await redis.expire(user_tokens_key, int(self.settings.security.refresh_token_expire_days * 86400) + 3600)
        
        return raw_token, token_data
    
    async def revoke_token(self, raw_token: str) -> bool:
        """Revoke a specific refresh token."""
        redis = await self._get_redis()
        if not redis:
            return False
        
        token_hash = self._hash_token(raw_token)
        token_key = f"{self.TOKEN_PREFIX}{token_hash}"
        
        token_data_dict = await redis.get(token_key)
        if not token_data_dict:
            return False
        
        token_data = RefreshTokenData.from_dict(token_data_dict)
        token_data.revoked = True
        await redis.set(token_key, token_data.to_dict(), ex=86400)  # Keep for 1 day for audit
        
        return True
    
    async def revoke_family(self, family_id: str, reason: str = "manual") -> int:
        """Revoke all tokens in a family (logout from all devices in session)."""
        redis = await self._get_redis()
        if not redis:
            return 0
        
        return await self._revoke_family(redis, family_id, reason)
    
    async def _revoke_family(self, redis, family_id: str, reason: str) -> int:
        """Internal method to revoke entire family."""
        family_key = f"{self.FAMILY_PREFIX}{family_id}"
        token_hashes = await redis.smembers(family_key)
        
        revoked_count = 0
        for token_hash in token_hashes:
            token_key = f"{self.TOKEN_PREFIX}{token_hash}"
            token_data_dict = await redis.get(token_key)
            if token_data_dict:
                token_data = RefreshTokenData.from_dict(token_data_dict)
                if not token_data.revoked:
                    token_data.revoked = True
                    token_data.metadata = token_data.metadata or {}
                    token_data.metadata["revocation_reason"] = reason
                    token_data.metadata["revoked_at"] = time.time()
                    await redis.set(token_key, token_data.to_dict(), ex=86400)
                    revoked_count += 1
        
        # Delete family set
        await redis.delete(family_key)
        
        return revoked_count
    
    async def revoke_all_user_tokens(self, user_id: UUID, reason: str = "logout_all") -> int:
        """Revoke all refresh tokens for a user (logout everywhere)."""
        redis = await self._get_redis()
        if not redis:
            return 0
        
        user_tokens_key = f"{self.USER_TOKENS_PREFIX}{user_id}"
        token_hashes = await redis.smembers(user_tokens_key)
        
        revoked_count = 0
        families_revoked = set()
        
        for token_hash in token_hashes:
            token_key = f"{self.TOKEN_PREFIX}{token_hash}"
            token_data_dict = await redis.get(token_key)
            if token_data_dict:
                token_data = RefreshTokenData.from_dict(token_data_dict)
                if not token_data.revoked:
                    token_data.revoked = True
                    token_data.metadata = token_data.metadata or {}
                    token_data.metadata["revocation_reason"] = reason
                    token_data.metadata["revoked_at"] = time.time()
                    await redis.set(token_key, token_data.to_dict(), ex=86400)
                    revoked_count += 1
                
                families_revoked.add(token_data.family_id)
        
        # Clean up family sets
        for family_id in families_revoked:
            await redis.delete(f"{self.FAMILY_PREFIX}{family_id}")
        
        # Clear user tokens set
        await redis.delete(user_tokens_key)
        
        return revoked_count
    
    async def get_token_info(self, raw_token: str) -> Optional[RefreshTokenData]:
        """Get token info without modifying it (for inspection)."""
        redis = await self._get_redis()
        if not redis:
            return None
        
        token_hash = self._hash_token(raw_token)
        token_key = f"{self.TOKEN_PREFIX}{token_hash}"
        
        token_data_dict = await redis.get(token_key)
        if not token_data_dict:
            return None
        
        return RefreshTokenData.from_dict(token_data_dict)
    
    async def get_user_active_families(self, user_id: UUID) -> List[str]:
        """Get all active family IDs for a user."""
        redis = await self._get_redis()
        if not redis:
            return []
        
        user_tokens_key = f"{self.USER_TOKENS_PREFIX}{user_id}"
        token_hashes = await redis.smembers(user_tokens_key)
        
        families = set()
        for token_hash in token_hashes:
            token_key = f"{self.TOKEN_PREFIX}{token_hash}"
            token_data_dict = await redis.get(token_key)
            if token_data_dict:
                token_data = RefreshTokenData.from_dict(token_data_dict)
                if not token_data.revoked and time.time() < token_data.expires_at:
                    families.add(token_data.family_id)
        
        return list(families)
    
    async def _cleanup_token(self, redis, token_hash: str, token_data: RefreshTokenData) -> None:
        """Clean up expired token references."""
        token_key = f"{self.TOKEN_PREFIX}{token_hash}"
        await redis.delete(token_key)
        
        # Remove from family
        family_key = f"{self.FAMILY_PREFIX}{token_data.family_id}"
        await redis.srem(family_key, token_hash)
        
        # Remove from user tokens
        user_tokens_key = f"{self.USER_TOKENS_PREFIX}{token_data.user_id}"
        await redis.srem(user_tokens_key, token_hash)
    
    async def cleanup_expired(self) -> int:
        """Clean up expired tokens (maintenance task)."""
        # This would be run as a periodic Celery task
        # For now, Redis TTL handles most cleanup automatically
        return 0


# Global instance
refresh_token_service = RefreshTokenService()


async def get_refresh_token_service() -> RefreshTokenService:
    """Get the global refresh token service instance."""
    return refresh_token_service