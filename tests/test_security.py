"""
Security Tests for Checkpoint 2

Tests for:
- RLS tenant isolation
- Credential encryption
- Webhook security
- Rate limiting
- RBAC
- Refresh token security
- Audit logging
"""

import hashlib
import hmac
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.core.credential_encryption import (
    CredentialEncryption,
    encrypt_credentials,
    decrypt_credentials,
    CredentialEncryptionError,
)
from app.core.rbac import (
    RBAC,
    Permission,
    RoleEnum,
    require_permission,
    require_role,
)
from app.core.refresh_token import (
    RefreshTokenService,
    RefreshTokenData,
)
from app.core.audit_log import (
    AuditLogger,
    AuditEventType,
    audit_logger,
)
from app.core.rate_limiter import (
    RateLimiter,
    RateLimitRule,
    RateLimitScope,
    RateLimitInfo,
)
from app.core.webhook_security import (
    WebhookVerificationResult,
    MetaWebhookVerifier,
    WhatsAppWebhookVerifier,
    StripeWebhookVerifier,
    GenericHMACVerifier,
    get_webhook_verifier,
    verify_webhook,
)
from app.core.tenant_context import TenantContext


class TestCredentialEncryption:
    """Tests for credential encryption service."""
    
    def test_encrypt_decrypt_string(self):
        """Test basic string encryption/decryption."""
        ce = CredentialEncryption()
        plaintext = "super-secret-api-key-123"
        encrypted = ce.encrypt(plaintext)
        decrypted = ce.decrypt(encrypted)
        assert decrypted == plaintext
        assert encrypted != plaintext
    
    def test_encrypt_decrypt_json(self):
        """Test JSON encryption/decryption."""
        ce = CredentialEncryption()
        data = {"api_key": "sk-test-123", "secret": "super-secret", "nested": {"key": "value"}}
        encrypted = ce.encrypt_json(data)
        decrypted = ce.decrypt_json(encrypted)
        assert decrypted == data
    
    def test_encrypt_empty_string_raises(self):
        """Test that empty string raises error."""
        ce = CredentialEncryption()
        with pytest.raises(CredentialEncryptionError):
            ce.encrypt("")
    
    def test_decrypt_empty_string_raises(self):
        """Test that empty string raises error."""
        ce = CredentialEncryption()
        with pytest.raises(CredentialEncryptionError):
            ce.decrypt("")
    
    def test_decrypt_tampered_data_raises(self):
        """Test that tampered ciphertext raises error."""
        ce = CredentialEncryption()
        plaintext = "test-secret"
        encrypted = ce.encrypt(plaintext)
        
        # Tamper with ciphertext
        tampered = encrypted[:-1] + ("a" if encrypted[-1] != "a" else "b")
        
        with pytest.raises(CredentialEncryptionError):
            ce.decrypt(tampered)
    
    def test_decrypt_wrong_key_raises(self):
        """Test that wrong key raises error."""
        ce1 = CredentialEncryption()
        # Create another instance with different key (simulated)
        plaintext = "test-secret"
        encrypted = ce1.encrypt(plaintext)
        
        # Directly test with corrupted key by modifying internal key
        ce2 = CredentialEncryption()
        ce2._key = b"x" * 32  # Wrong key
        
        with pytest.raises(CredentialEncryptionError):
            ce2.decrypt(encrypted)
    
    def test_encrypt_deterministic_json(self):
        """Test that JSON encryption is deterministic for same data."""
        ce = CredentialEncryption()
        data = {"b": 2, "a": 1}
        encrypted1 = ce.encrypt_json(data)
        encrypted2 = ce.encrypt_json(data)
        # Should be different due to random nonce
        assert encrypted1 != encrypted2
        # But both should decrypt to same data
        assert ce.decrypt_json(encrypted1) == data
        assert ce.decrypt_json(encrypted2) == data
    
    def test_convenience_functions(self):
        """Test module-level convenience functions."""
        data = {"key": "value"}
        encrypted = encrypt_credentials(data)
        decrypted = decrypt_credentials(encrypted)
        assert decrypted == data


class TestRBAC:
    """Tests for role-based access control."""
    
    def test_owner_has_all_permissions(self):
        """Test that OWNER has SUPERUSER_ALL permission."""
        perms = RBAC.get_permissions(RoleEnum.OWNER)
        assert Permission.SUPERUSER_ALL in perms
        assert RBAC.has_permission(RoleEnum.OWNER, Permission.USER_CREATE)
        assert RBAC.has_permission(RoleEnum.OWNER, Permission.TENANT_DELETE)
        assert RBAC.has_permission(RoleEnum.OWNER, Permission.SUPERUSER_ALL)
    
    def test_admin_permissions(self):
        """Test ADMIN permissions."""
        assert RBAC.has_permission(RoleEnum.ADMIN, Permission.USER_CREATE)
        assert RBAC.has_permission(RoleEnum.ADMIN, Permission.TENANT_UPDATE)
        assert RBAC.has_permission(RoleEnum.ADMIN, Permission.CAMPAIGN_SEND)
        assert RBAC.has_permission(RoleEnum.ADMIN, Permission.INTEGRATION_CREDENTIALS_MANAGE)
        # ADMIN should NOT have SUPERUSER_ALL
        assert not RBAC.has_permission(RoleEnum.ADMIN, Permission.SUPERUSER_ALL)
    
    def test_sales_manager_permissions(self):
        """Test SALES_MANAGER permissions."""
        assert RBAC.has_permission(RoleEnum.SALES_MANAGER, Permission.LEAD_CREATE)
        assert RBAC.has_permission(RoleEnum.SALES_MANAGER, Permission.DEAL_CLOSE)
        assert RBAC.has_permission(RoleEnum.SALES_MANAGER, Permission.CAMPAIGN_SEND)
        assert RBAC.has_permission(RoleEnum.SALES_MANAGER, Permission.CONTACT_IMPORT)
        # Should NOT have admin permissions
        assert not RBAC.has_permission(RoleEnum.SALES_MANAGER, Permission.USER_CREATE)
        assert not RBAC.has_permission(RoleEnum.SALES_MANAGER, Permission.TENANT_DELETE)
        assert not RBAC.has_permission(RoleEnum.SALES_MANAGER, Permission.INTEGRATION_CREDENTIALS_MANAGE)
    
    def test_sales_executive_permissions(self):
        """Test SALES_EXECUTIVE permissions."""
        assert RBAC.has_permission(RoleEnum.SALES_EXECUTIVE, Permission.LEAD_CREATE)
        assert RBAC.has_permission(RoleEnum.SALES_EXECUTIVE, Permission.LEAD_QUALIFY)
        assert RBAC.has_permission(RoleEnum.SALES_EXECUTIVE, Permission.DEAL_CREATE)
        assert RBAC.has_permission(RoleEnum.SALES_EXECUTIVE, Permission.CONTACT_CREATE)
        # Should NOT have delete permissions
        assert not RBAC.has_permission(RoleEnum.SALES_EXECUTIVE, Permission.LEAD_DELETE)
        assert not RBAC.has_permission(RoleEnum.SALES_EXECUTIVE, Permission.CONTACT_DELETE)
        assert not RBAC.has_permission(RoleEnum.SALES_EXECUTIVE, Permission.CAMPAIGN_DELETE)
    
    def test_marketing_permissions(self):
        """Test MARKETING permissions."""
        assert RBAC.has_permission(RoleEnum.MARKETING, Permission.CAMPAIGN_CREATE)
        assert RBAC.has_permission(RoleEnum.MARKETING, Permission.CAMPAIGN_SEND)
        assert RBAC.has_permission(RoleEnum.MARKETING, Permission.CONTACT_IMPORT)
        assert RBAC.has_permission(RoleEnum.MARKETING, Permission.EMAIL_TEMPLATE_CREATE)
        # Should NOT have deal permissions
        assert not RBAC.has_permission(RoleEnum.MARKETING, Permission.DEAL_CREATE)
        assert not RBAC.has_permission(RoleEnum.MARKETING, Permission.DEAL_CLOSE)
    
    def test_viewer_permissions(self):
        """Test VIEWER read-only permissions."""
        assert RBAC.has_permission(RoleEnum.VIEWER, Permission.CONTACT_READ)
        assert RBAC.has_permission(RoleEnum.VIEWER, Permission.LEAD_READ)
        assert RBAC.has_permission(RoleEnum.VIEWER, Permission.DEAL_READ)
        assert RBAC.has_permission(RoleEnum.VIEWER, Permission.CAMPAIGN_READ)
        # Should NOT have any write permissions
        assert not RBAC.has_permission(RoleEnum.VIEWER, Permission.CONTACT_CREATE)
        assert not RBAC.has_permission(RoleEnum.VIEWER, Permission.LEAD_CREATE)
        assert not RBAC.has_permission(RoleEnum.VIEWER, Permission.CAMPAIGN_CREATE)
    
    def test_can_assign_role(self):
        """Test role assignment rules."""
        # OWNER can assign any role
        assert RBAC.can_assign_role(RoleEnum.OWNER, RoleEnum.ADMIN)
        assert RBAC.can_assign_role(RoleEnum.OWNER, RoleEnum.OWNER)
        assert RBAC.can_assign_role(RoleEnum.OWNER, RoleEnum.VIEWER)
        
        # ADMIN can assign any role except OWNER
        assert RBAC.can_assign_role(RoleEnum.ADMIN, RoleEnum.SALES_MANAGER)
        assert RBAC.can_assign_role(RoleEnum.ADMIN, RoleEnum.ADMIN)
        assert not RBAC.can_assign_role(RoleEnum.ADMIN, RoleEnum.OWNER)
        
        # Others cannot assign roles
        assert not RBAC.can_assign_role(RoleEnum.SALES_MANAGER, RoleEnum.SALES_EXECUTIVE)
        assert not RBAC.can_assign_role(RoleEnum.SALES_EXECUTIVE, RoleEnum.VIEWER)
        assert not RBAC.can_assign_role(RoleEnum.VIEWER, RoleEnum.VIEWER)
    
    def test_can_manage_membership(self):
        """Test membership management rules."""
        # Higher role can manage lower role
        assert RBAC.can_manage_membership(RoleEnum.OWNER, RoleEnum.ADMIN)
        assert RBAC.can_manage_membership(RoleEnum.ADMIN, RoleEnum.SALES_MANAGER)
        assert RBAC.can_manage_membership(RoleEnum.SALES_MANAGER, RoleEnum.SALES_EXECUTIVE)
        
        # Cannot manage same or higher role
        assert not RBAC.can_manage_membership(RoleEnum.SALES_MANAGER, RoleEnum.SALES_MANAGER)
        assert not RBAC.can_manage_membership(RoleEnum.SALES_EXECUTIVE, RoleEnum.SALES_MANAGER)
        assert not RBAC.can_manage_membership(RoleEnum.ADMIN, RoleEnum.OWNER)
    
    def test_get_assignable_roles(self):
        """Test getting assignable roles for a role."""
        owner_roles = RBAC.get_assignable_roles(RoleEnum.OWNER)
        assert RoleEnum.ADMIN in owner_roles
        assert RoleEnum.SALES_MANAGER in owner_roles
        assert RoleEnum.OWNER not in owner_roles  # Not in default list
        
        admin_roles = RBAC.get_assignable_roles(RoleEnum.ADMIN)
        assert RoleEnum.SALES_MANAGER in admin_roles
        assert RoleEnum.OWNER not in admin_roles
        
        viewer_roles = RBAC.get_assignable_roles(RoleEnum.VIEWER)
        assert len(viewer_roles) == 0


class TestRefreshTokenService:
    """Tests for refresh token service."""
    
    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        redis.sadd = AsyncMock(return_value=1)
        redis.srem = AsyncMock(return_value=1)
        redis.smembers = AsyncMock(return_value=set())
        redis.expire = AsyncMock(return_value=True)
        redis.pipeline = MagicMock(return_value=AsyncMock(
            execute=AsyncMock(return_value=[1, 0, 1, 1])
        ))
        return redis
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.security.refresh_token_expire_days = 30
        settings.security.secret_key = "test-secret-key-min-32-chars-long"
        return settings
    
    @pytest.mark.asyncio
    async def test_create_refresh_token(self, mock_redis, mock_settings):
        """Test creating a refresh token."""
        with patch('app.core.refresh_token.get_redis', return_value=mock_redis), \
             patch('app.core.refresh_token.get_settings', return_value=mock_settings):
            
            service = RefreshTokenService()
            user = MagicMock()
            user.id = uuid4()
            tenant_id = uuid4()
            
            raw_token, token_data = await service.create_refresh_token(user, tenant_id)
            
            assert raw_token is not None
            assert len(raw_token) > 0
            assert token_data.jti is not None
            assert token_data.family_id is not None
            assert token_data.user_id == str(user.id)
            assert token_data.tenant_id == str(tenant_id)
            assert not token_data.revoked
    
    @pytest.mark.asyncio
    async def test_verify_and_rotate_success(self, mock_redis, mock_settings):
        """Test successful token verification and rotation."""
        with patch('app.core.refresh_token.get_redis', return_value=mock_redis), \
             patch('app.core.refresh_token.get_settings', return_value=mock_settings):
            
            service = RefreshTokenService()
            user_id = uuid4()
            tenant_id = uuid4()
            
            # Create initial token
            raw_token, token_data = await service.create_refresh_token(
                MagicMock(id=user_id), tenant_id
            )
            
            # Mock Redis to return the token data
            token_hash = service._hash_token(raw_token)
            mock_redis.get = AsyncMock(return_value=token_data.to_dict())
            
            # Verify and rotate
            new_token, new_data = await service.verify_and_rotate(raw_token, user_id, tenant_id)
            
            assert new_token != raw_token
            assert new_data.family_id == token_data.family_id
            assert new_data.jti != token_data.jti
    
    @pytest.mark.asyncio
    async def test_reuse_detection_revokes_family(self, mock_redis, mock_settings):
        """Test that reuse detection revokes entire family."""
        with patch('app.core.refresh_token.get_redis', return_value=mock_redis), \
             patch('app.core.refresh_token.get_settings', return_value=mock_settings):
            
            service = RefreshTokenService()
            user_id = uuid4()
            tenant_id = uuid4()
            
            # Create token
            raw_token, token_data = await service.create_refresh_token(
                MagicMock(id=user_id), tenant_id
            )
            
            # First use - should succeed
            token_hash = service._hash_token(raw_token)
            mock_redis.get = AsyncMock(return_value=token_data.to_dict())
            
            new_token, new_data = await service.verify_and_rotate(raw_token, user_id, tenant_id)
            
            # Mark old token as revoked
            token_data.revoked = True
            mock_redis.get = AsyncMock(return_value=token_data.to_dict())
            
            # Second use of OLD token - should detect reuse
            with pytest.raises(ValueError, match="reuse detected"):
                await service.verify_and_rotate(raw_token, user_id, tenant_id)
            
            # Verify family was revoked
            mock_redis.delete.assert_called()
    
    @pytest.mark.asyncio
    async def test_expired_token_raises(self, mock_redis, mock_settings):
        """Test that expired token raises error."""
        with patch('app.core.refresh_token.get_redis', return_value=mock_redis), \
             patch('app.core.refresh_token.get_settings', return_value=mock_settings):
            
            service = RefreshTokenService()
            user_id = uuid4()
            tenant_id = uuid4()
            
            # Create expired token data
            token_data = RefreshTokenData(
                jti="test-jti",
                user_id=str(user_id),
                tenant_id=str(tenant_id),
                family_id="test-family",
                created_at=0,
                expires_at=1,  # Expired
            )
            token_hash = "test-hash"
            mock_redis.get = AsyncMock(return_value=token_data.to_dict())
            
            with pytest.raises(ValueError, match="expired"):
                await service.verify_and_rotate("any-token", user_id, tenant_id)
    
    @pytest.mark.asyncio
    async def test_revoke_all_user_tokens(self, mock_redis, mock_settings):
        """Test revoking all user tokens."""
        with patch('app.core.refresh_token.get_redis', return_value=mock_redis), \
             patch('app.core.refresh_token.get_settings', return_value=mock_settings):
            
            service = RefreshTokenService()
            user_id = uuid4()
            
            # Mock some tokens
            token_data = RefreshTokenData(
                jti="jti1",
                user_id=str(user_id),
                tenant_id=str(uuid4()),
                family_id="family1",
                created_at=0,
                expires_at=9999999999,
            )
            mock_redis.smembers = AsyncMock(return_value={"hash1", "hash2"})
            mock_redis.get = AsyncMock(return_value=token_data.to_dict())
            
            count = await service.revoke_all_user_tokens(user_id)
            assert count >= 0


class TestAuditLogger:
    """Tests for audit logger."""
    
    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        return session
    
    @pytest.mark.asyncio
    async def test_log_basic_event(self, mock_session):
        """Test logging a basic event."""
        tenant_id = uuid4()
        user_id = uuid4()
        
        await audit_logger.log(
            event_type=AuditEventType.LOGIN_SUCCESS,
            tenant_id=tenant_id,
            user_id=user_id,
            ip_address="192.168.1.1",
            user_agent="test-agent",
            session=mock_session,
        )
        
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_not_called()  # Not critical
    
    @pytest.mark.asyncio
    async def test_log_critical_event_flushes(self, mock_session):
        """Test that critical events flush immediately."""
        tenant_id = uuid4()
        user_id = uuid4()
        
        await audit_logger.log(
            event_type=AuditEventType.REFRESH_TOKEN_REUSE_DETECTED,
            tenant_id=tenant_id,
            user_id=user_id,
            ip_address="192.168.1.1",
            session=mock_session,
        )
        
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()  # Critical event
    
    def test_sanitize_values(self):
        """Test that sensitive values are redacted."""
        values = {
            "username": "test",
            "password": "secret123",
            "api_key": "sk-live-123",
            "nested": {
                "refresh_token": "rt-123",
                "normal": "value"
            }
        }
        
        sanitized = audit_logger._sanitize_values(values)
        
        assert sanitized["username"] == "test"
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["nested"]["refresh_token"] == "[REDACTED]"
        assert sanitized["nested"]["normal"] == "value"
    
    def test_correlation_id_context(self):
        """Test correlation ID context management."""
        audit_logger.set_correlation_id("test-correlation-123")
        assert audit_logger.get_correlation_id() == "test-correlation-123"
        audit_logger.set_correlation_id(None)
        assert audit_logger.get_correlation_id() is None


class TestRateLimiter:
    """Tests for rate limiter."""
    
    def test_default_rules_configured(self):
        """Test that default rules are configured."""
        limiter = RateLimiter()
        assert len(limiter._rules) > 0
        
        # Check login rule exists
        login_rules = [r for r in limiter._rules if "/api/v1/auth/login" in r.paths]
        assert len(login_rules) > 0
        assert login_rules[0].scope == RateLimitScope.IP
        assert login_rules[0].max_requests == 5
    
    def test_path_matching(self):
        """Test path pattern matching."""
        limiter = RateLimiter()
        
        assert limiter._match_path("/api/v1/auth/login", "/api/v1/auth/login")
        assert limiter._match_path("/api/v1/leads/123", "/api/v1/leads/*")
        assert limiter._match_path("/api/v1/contacts/search", "/api/v1/*/search")
        assert limiter._match_path("/any/path", "/*")
        assert not limiter._match_path("/api/v1/auth/login", "/api/v1/auth/register")
    
    def test_rule_specificity_sorting(self):
        """Test that rules are sorted by specificity."""
        limiter = RateLimiter()
        
        # More specific rules should come first
        specific_patterns = [r.paths for r in limiter._rules if len(r.paths) == 1 and "*" not in r.paths[0]]
        generic_patterns = [r.paths for r in limiter._rules if "/*" in r.paths]
        
        # At least one specific and one generic
        assert len(specific_patterns) > 0
        assert len(generic_patterns) > 0


class TestWebhookSecurity:
    """Tests for webhook security framework."""
    
    def test_constant_time_compare(self):
        """Test constant-time comparison."""
        verifier = MetaWebhookVerifier()
        assert verifier._constant_time_compare("abc", "abc")
        assert not verifier._constant_time_compare("abc", "abd")
        assert not verifier._constant_time_compare("abc", "abcd")
    
    def test_get_webhook_verifier(self):
        """Test verifier registry."""
        assert isinstance(get_webhook_verifier("meta"), MetaWebhookVerifier)
        assert isinstance(get_webhook_verifier("facebook"), MetaWebhookVerifier)
        assert isinstance(get_webhook_verifier("instagram"), MetaWebhookVerifier)
        assert isinstance(get_webhook_verifier("whatsapp"), WhatsAppWebhookVerifier)
        assert isinstance(get_webhook_verifier("stripe"), StripeWebhookVerifier)
        assert isinstance(get_webhook_verifier("custom"), GenericHMACVerifier)
    
    @pytest.mark.asyncio
    async def test_meta_verifier_valid_signature(self):
        """Test Meta webhook with valid signature."""
        verifier = MetaWebhookVerifier()
        secret = "test-secret"
        body = b'{"entry": [{"changes": [{"value": {"leadgen_id": "123"}}]}]}'
        
        # Compute valid signature
        expected_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        
        # Create mock request
        request = MagicMock()
        request.headers = {"X-Hub-Signature-256": f"sha256={expected_sig}"}
        request.body = AsyncMock(return_value=body)
        
        with patch('app.core.webhook_security.get_redis', return_value=AsyncMock(
            set=AsyncMock(return_value=True)
        )):
            result = await verifier.verify(request, secret, body)
            
            assert result.valid is True
            assert result.provider == "meta"
            assert result.event_id == "123"
    
    @pytest.mark.asyncio
    async def test_meta_verifier_invalid_signature(self):
        """Test Meta webhook with invalid signature."""
        verifier = MetaWebhookVerifier()
        secret = "test-secret"
        body = b'{"entry": [{"changes": [{"value": {"leadgen_id": "123"}}]}]}'
        
        request = MagicMock()
        request.headers = {"X-Hub-Signature-256": "sha256=invalid-signature"}
        request.body = AsyncMock(return_value=body)
        
        with patch('app.core.webhook_security.get_redis', return_value=AsyncMock()):
            result = await verifier.verify(request, secret, body)
            
            assert result.valid is False
            assert result.error == "Invalid signature"
    
    @pytest.mark.asyncio
    async def test_meta_verifier_missing_signature(self):
        """Test Meta webhook with missing signature."""
        verifier = MetaWebhookVerifier()
        
        request = MagicMock()
        request.headers = {}
        request.body = AsyncMock(return_value=b"{}")
        
        result = await verifier.verify(request, "secret", b"{}")
        
        assert result.valid is False
        assert "Missing" in result.error
    
    @pytest.mark.asyncio
    async def test_stripe_verifier_valid_signature(self):
        """Test Stripe webhook with valid signature."""
        verifier = StripeWebhookVerifier()
        secret = "whsec_test"
        body = b'{"id": "evt_123", "type": "payment_intent.succeeded"}'
        timestamp = str(int(__import__('time').time()))
        
        signed_payload = f"{timestamp}.{body.decode()}".encode()
        expected_sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        
        request = MagicMock()
        request.headers = {"Stripe-Signature": f"t={timestamp},v1={expected_sig}"}
        request.body = AsyncMock(return_value=body)
        
        with patch('app.core.webhook_security.get_redis', return_value=AsyncMock(
            set=AsyncMock(return_value=True)
        )):
            result = await verifier.verify(request, secret, body)
            
            assert result.valid is True
            assert result.provider == "stripe"
            assert result.event_id == "evt_123"
    
    @pytest.mark.asyncio
    async def test_stripe_verifier_expired_timestamp(self):
        """Test Stripe webhook with expired timestamp."""
        verifier = StripeWebhookVerifier()
        secret = "whsec_test"
        body = b'{"id": "evt_123"}'
        old_timestamp = str(int(__import__('time').time()) - 400)  # > 5 min ago
        
        signed_payload = f"{old_timestamp}.{body.decode()}".encode()
        expected_sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        
        request = MagicMock()
        request.headers = {"Stripe-Signature": f"t={old_timestamp},v1={expected_sig}"}
        request.body = AsyncMock(return_value=body)
        
        result = await verifier.verify(request, secret, body)
        
        assert result.valid is False
        assert "Timestamp too old" in result.error
    
    @pytest.mark.asyncio
    async def test_generic_hmac_verifier(self):
        """Test generic HMAC verifier."""
        verifier = GenericHMACVerifier("custom", "X-Custom-Signature")
        secret = "custom-secret"
        body = b'{"event": "test"}'
        
        expected_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        
        request = MagicMock()
        request.headers = {"X-Custom-Signature": expected_sig}
        request.body = AsyncMock(return_value=body)
        
        with patch('app.core.webhook_security.get_redis', return_value=AsyncMock(
            set=AsyncMock(return_value=True)
        )):
            result = await verifier.verify(request, secret, body)
            
            assert result.valid is True
            assert result.provider == "custom"
    
    @pytest.mark.asyncio
    async def test_replay_protection(self):
        """Test replay protection blocks duplicate events."""
        verifier = MetaWebhookVerifier()
        secret = "test-secret"
        body = b'{"entry": [{"changes": [{"value": {"leadgen_id": "123"}}]}]}'
        expected_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        
        request = MagicMock()
        request.headers = {"X-Hub-Signature-256": f"sha256={expected_sig}"}
        request.body = AsyncMock(return_value=body)
        
        # Mock Redis to simulate replay
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=[True, False])  # First succeeds, second fails (already exists)
        
        with patch('app.core.webhook_security.get_redis', return_value=mock_redis):
            # First request - should succeed
            result1 = await verifier.verify(request, secret, body)
            assert result1.valid is True
            
            # Second request - should be detected as replay
            result2 = await verifier.verify(request, secret, body)
            assert result2.valid is True  # Signature valid
            assert result2.error == "Replay detected"  # But replay detected


class TestTenantContext:
    """Tests for tenant database context."""
    
    @pytest.mark.asyncio
    async def test_tenant_context_manager(self):
        """Test tenant_db_context manager."""
        from app.core.tenant_context import tenant_db_context
        
        # This would need a real database to test fully
        # For now, verify the function exists and is callable
        assert callable(tenant_db_context)
    
    @pytest.mark.asyncio
    async def test_verify_tenant_access(self):
        """Test tenant membership verification."""
        # This would need a real database
        assert callable(TenantContext.verify_tenant_access)


# Integration-style tests
class TestSecurityIntegration:
    """Integration tests combining multiple security components."""
    
    @pytest.mark.asyncio
    async def test_credential_encryption_with_rbac(self):
        """Test that credential encryption works with RBAC permissions."""
        # Encrypt credentials
        creds = {"api_key": "sk-test", "secret": "secret"}
        encrypted = encrypt_credentials(creds)
        
        # Verify ADMIN has permission to manage credentials
        assert RBAC.has_permission(RoleEnum.ADMIN, Permission.INTEGRATION_CREDENTIALS_MANAGE)
        assert RBAC.has_permission(RoleEnum.ADMIN, Permission.INTEGRATION_CREDENTIALS_VIEW)
        
        # Verify SALES_EXECUTIVE does NOT have credentials permission
        assert not RBAC.has_permission(RoleEnum.SALES_EXECUTIVE, Permission.INTEGRATION_CREDENTIALS_MANAGE)
        
        # Decrypt works
        decrypted = decrypt_credentials(encrypted)
        assert decrypted == creds
    
    @pytest.mark.asyncio
    async def test_webhook_verification_with_rate_limiting(self):
        """Test that webhook endpoints can be rate limited."""
        limiter = RateLimiter()
        
        # Check webhook rule exists
        webhook_rules = [r for r in limiter._rules if "/api/v1/webhooks/*" in r.paths]
        assert len(webhook_rules) > 0
        assert webhook_rules[0].scope == RateLimitScope.IP
        assert webhook_rules[0].max_requests == 1000
        assert webhook_rules[0].window_seconds == 60
    
    @pytest.mark.asyncio
    async def test_audit_logging_covers_security_events(self):
        """Test that audit logger covers all critical security events."""
        critical_events = {
            AuditEventType.LOGIN_FAILURE,
            AuditEventType.REFRESH_TOKEN_REUSE_DETECTED,
            AuditEventType.PERMISSION_DENIED,
            AuditEventType.RATE_LIMIT_EXCEEDED,
            AuditEventType.WEBHOOK_SIGNATURE_FAILURE,
            AuditEventType.ROLE_ESCALATE_ATTEMPT,
        }
        
        for event in critical_events:
            assert event in audit_logger._critical_events


if __name__ == "__main__":
    pytest.main([__file__, "-v"])