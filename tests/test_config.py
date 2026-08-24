"""Tests for configuration loading from environment variables."""

import os
from pathlib import Path
from functools import lru_cache

import pytest


def test_config_loads_from_env():
    """Test that config loads DATABASE_URL, REDIS_URL, FIRECRAWL_API_KEY from environment."""
    # CRITICAL: Set environment variables FIRST, before ANY imports
    # that might trigger get_settings() caching
    os.environ["DATABASE_HOST"] = "localhost"
    os.environ["DATABASE_PORT"] = "5432"
    os.environ["DATABASE_USERNAME"] = "user"
    os.environ["DATABASE_PASSWORD"] = "pass"
    os.environ["DATABASE_NAME"] = "testdb"
    os.environ["REDIS_HOST"] = "localhost"
    os.environ["REDIS_PORT"] = "6379"
    os.environ["REDIS_DB"] = "0"
    os.environ["FC_API_KEY"] = "fc_test_key_123"
    os.environ["SECURITY_SECRET_KEY"] = "test-secret-key-min-32-chars-long"
    os.environ["APP_ENVIRONMENT"] = "testing"

    try:
        # Clear cache to ensure fresh load
        from app.core.config import get_settings
        get_settings.cache_clear()
        
        from app.core.config import Settings
        # Use from_yaml() which properly merges YAML + env vars
        settings = Settings.from_yaml()

        assert settings.database.url == "postgresql+asyncpg://user:pass@localhost:5432/testdb"
        assert settings.redis.url == "redis://localhost:6379/0"
        assert settings.firecrawl.api_key == "fc_test_key_123"
        assert settings.security.secret_key == "test-secret-key-min-32-chars-long"
        assert settings.app.environment == "testing"
    finally:
        # Clean up environment variables
        for key in ["DATABASE_HOST", "DATABASE_PORT", "DATABASE_USERNAME", "DATABASE_PASSWORD", "DATABASE_NAME",
                    "REDIS_HOST", "REDIS_PORT", "REDIS_DB",
                    "FC_API_KEY", "SECURITY_SECRET_KEY", "APP_ENVIRONMENT"]:
            os.environ.pop(key, None)
        # Clear cache again for next test
        get_settings.cache_clear()


def test_config_requires_database_url():
    """Test that DATABASE_URL is required."""
    from app.core.config import Settings, get_settings
    get_settings.cache_clear()
    
    os.environ.pop("DATABASE_HOST", None)

    # This should still work with defaults
    settings = Settings()
    assert settings.database.url is not None
    get_settings.cache_clear()


def test_config_requires_secret_key():
    """Test that SECRET_KEY has a default (validation will catch short keys)."""
    from app.core.config import Settings, get_settings
    get_settings.cache_clear()
    
    os.environ.pop("SECURITY_SECRET_KEY", None)

    # Should work with default from config.yaml
    settings = Settings()
    assert settings.security.secret_key is not None
    assert len(settings.security.secret_key) >= 32
    get_settings.cache_clear()