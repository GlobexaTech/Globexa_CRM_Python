"""Tests for deterministic YAML/.env/environment configuration precedence."""

from pathlib import Path

from app.core.config import Settings


CONFIG_ENV_KEYS = (
    "APP_ENVIRONMENT",
    "APP_DEBUG",
    "APP__ENVIRONMENT",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_USERNAME",
    "DATABASE_PASSWORD",
    "DATABASE_NAME",
    "DATABASE__HOST",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_DB",
    "REDIS_PASSWORD",
    "REDIS__HOST",
    "SECURITY_SECRET_KEY",
    "SECURITY__SECRET_KEY",
    "FIRECRAWL_API_KEY",
    "FIRECRAWL__API_KEY",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "CELERY__BROKER_URL",
    "CELERY__RESULT_BACKEND",
)


def _clear_config_env(monkeypatch) -> None:
    for key in CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _write_test_yaml(path: Path) -> Path:
    path.write_text(
        """
app:
  environment: development
  debug: true
database:
  host: postgres
  port: 5432
  username: postgres
  password: postgres
  name: globexa_crm
redis:
  host: redis
  port: 6379
  db: 0
security:
  secret_key: CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY
firecrawl:
  api_key: ""
celery:
  broker_url: redis://redis:6379/0
  result_backend: redis://redis:6379/0
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def test_config_loads_conventional_env_overrides(monkeypatch, tmp_path):
    """Single-prefix env vars used by Docker/.env override YAML values."""
    _clear_config_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    yaml_path = _write_test_yaml(tmp_path / "config.yaml")

    monkeypatch.setenv("APP_ENVIRONMENT", "testing")
    monkeypatch.setenv("DATABASE_HOST", "127.0.0.1")
    monkeypatch.setenv("SECURITY_SECRET_KEY", "test-secret-key-min-32-chars-long")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc_test_key_123")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/9")

    settings = Settings.from_yaml(str(yaml_path))

    assert settings.app.environment == "testing"
    assert settings.database.host == "127.0.0.1"
    assert settings.security.secret_key == "test-secret-key-min-32-chars-long"
    assert settings.firecrawl.api_key == "fc_test_key_123"
    assert settings.celery.broker_url == "redis://127.0.0.1:6379/9"


def test_config_supports_nested_env_overrides(monkeypatch, tmp_path):
    """Double-underscore nested env vars remain supported for container deployments."""
    _clear_config_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    yaml_path = _write_test_yaml(tmp_path / "config.yaml")

    monkeypatch.setenv("APP__ENVIRONMENT", "testing-nested")
    monkeypatch.setenv("DATABASE__HOST", "db.internal")
    monkeypatch.setenv("CELERY__RESULT_BACKEND", "redis://redis.internal:6379/4")

    settings = Settings.from_yaml(str(yaml_path))

    assert settings.app.environment == "testing-nested"
    assert settings.database.host == "db.internal"
    assert settings.celery.result_backend == "redis://redis.internal:6379/4"


def test_config_uses_yaml_defaults(monkeypatch, tmp_path):
    """YAML values are used when no process or local .env overrides exist."""
    _clear_config_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    yaml_path = _write_test_yaml(tmp_path / "config.yaml")

    settings = Settings.from_yaml(str(yaml_path))

    assert settings.database.url == (
        "postgresql+asyncpg://postgres:postgres@postgres:5432/globexa_crm"
    )
    assert settings.redis.url == "redis://redis:6379/0"
    assert settings.app.environment == "development"
    assert settings.celery.broker_url == "redis://redis:6379/0"


def test_config_secret_key_is_valid(monkeypatch, tmp_path):
    """YAML security defaults satisfy the minimum JWT secret length."""
    _clear_config_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    yaml_path = _write_test_yaml(tmp_path / "config.yaml")

    settings = Settings.from_yaml(str(yaml_path))

    assert len(settings.security.secret_key) >= 32
