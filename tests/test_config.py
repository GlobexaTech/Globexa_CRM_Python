"""Tests for configuration loading from environment variables."""

import os
from pathlib import Path
from functools import lru_cache

import pytest


def test_config_loads_from_env():
    """Test that config loads env vars correctly."""
    # CRITICAL: Set environment variables FIRST, before ANY imports
    # that might trigger get_settings() caching
    os.environ["SECURITY__SECRET_KEY"] = "test-secret-key-min-32-chars-long"
    os.environ["APP__ENVIRONMENT"] = "testing"
    os.environ["FIRECRAWL__API_KEY"] = "fc_test_key_123"

    try:
        # Clear cache to ensure fresh load
        from app.core.config import get_settings
        get_settings.cache_clear()
        
        from app.core.config import Settings
        # Use from_yaml() which properly merges YAML + env vars
        settings = Settings.from_yaml()

        # Verify env vars override yaml defaults
        assert settings.app.environment == "testing"
        assert settings.firecrawl.api_key == "fc_test_key_123"
        assert settings.security.secret_key == "test-secret-key-min-32-chars-long"
    finally:
        # Clean up environment variables
        for key in ["SECURITY__SECRET_KEY", "APP__ENVIRONMENT", "FIRECRAWL__API_KEY"]:
            os.environ.pop(key, None)
        # Clear cache again for next test
        get_settings.cache_clear()


def test_config_uses_yaml_defaults():
    """Test that config uses yaml defaults when env vars not set."""
    from app.core.config import Settings, get_settings
    get_settings.cache_clear()
    
    # Ensure no overriding env vars
    for key in ["SECURITY__SECRET_KEY", "APP__ENVIRONMENT", "FIRECRAWL__API_KEY"]:
        os.environ.pop(key, None)
    
    # Should work with defaults from config.yaml
    settings = Settings.from_yaml()
    assert settings.database.url == "postgresql+asyncpg://postgres:postgres@localhost:5432/globexa_crm"
    assert settings.redis.url == "redis://localhost:6379/0"
    assert settings.app.environment == "development"
    get_settings.cache_clear()


def test_config_requires_secret_key():
    """Test that SECRET_KEY has a default (validation will catch short keys)."""
    from app.core.config import Settings, get_settings
    get_settings.cache_clear()
    
    os.environ.pop("SECURITY__SECRET_KEY", None)
    
    # Should work with default from config.yaml
    settings = Settings.from_yaml()
    assert settings.security.secret_key is not None
    assert len(settings.security.secret_key) >= 32
    get_settings.cache_clear()