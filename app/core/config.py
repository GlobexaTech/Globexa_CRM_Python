"""
Configuration management for Globexa CRM.
Uses Pydantic Settings with YAML config file + environment variable overrides.
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from functools import lru_cache

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvFirstSettings(BaseSettings):
    """Base settings model with deterministic env/.env > init/YAML precedence."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Environment and .env values must override YAML values supplied as init kwargs.
        return env_settings, dotenv_settings, init_settings, file_secret_settings


class AppSettings(EnvFirstSettings):
    name: str = "Globexa CRM"
    version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True
    # Container listen address; published ports are controlled by deployment.
    host: str = "0.0.0.0"  # nosec B104
    port: int = 8000
    cors_origins: List[str] = []

    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")


class DatabaseSettings(EnvFirstSettings):
    host: str = "localhost"
    port: int = 5432
    username: str = "postgres"
    password: str = "postgres"
    name: str = "globexa_crm"
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False

    model_config = SettingsConfigDict(env_prefix="DATABASE_", extra="ignore")

    @property
    def url(self) -> str:
        """Build asyncpg connection URL."""
        return (
            f"postgresql+asyncpg://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @property
    def sync_url(self) -> str:
        """Build sync psycopg2 connection URL for Alembic."""
        return (
            f"postgresql://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class RedisSettings(EnvFirstSettings):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    max_connections: int = 50

    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")

    @property
    def url(self) -> str:
        """Build Redis connection URL."""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class FirecrawlSettings(EnvFirstSettings):
    api_key: str = ""

    model_config = SettingsConfigDict(env_prefix="FIRECRAWL_", extra="ignore")

    @field_validator("api_key", mode="before")
    @classmethod
    def validate_api_key(cls, v):
        if v is None:
            return ""
        return str(v)


class SecuritySettings(EnvFirstSettings):
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY_MIN_32_CHARS"
    credential_encryption_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    password_min_length: int = 8
    bcrypt_rounds: int = 12

    model_config = SettingsConfigDict(env_prefix="SECURITY_", extra="ignore")

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v


class GoogleOAuthSettings(EnvFirstSettings):
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    scopes: List[str] = ["openid", "email", "profile"]

    model_config = SettingsConfigDict(env_prefix="GOOGLE_", extra="ignore")

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


class LocalAISettings(EnvFirstSettings):
    enabled: bool = True
    base_url: str = "http://localhost:11434"
    default_model: str = "llama3.2:3b"
    timeout_seconds: int = 60
    suitable_tasks: List[str] = [
        "classification",
        "simple_scoring",
        "extraction",
        "summarization",
        "intent_identification",
        "tagging",
        "routing_decision",
    ]

    model_config = SettingsConfigDict(env_prefix="OLLAMA_", extra="ignore", nested_delimiter="__")


class CloudProviderSettings(EnvFirstSettings):
    enabled: bool = False
    api_key_env: str = ""
    base_url: str = ""
    models: List[str] = []
    default_model: str = ""

    model_config = SettingsConfigDict(extra="ignore", nested_delimiter="__")

    def get_api_key(self) -> Optional[str]:
        if self.api_key_env:
            return os.getenv(self.api_key_env)
        return None


class CloudAISettings(EnvFirstSettings):
    default_provider: str = "nvidia"
    providers: Dict[str, CloudProviderSettings] = {}

    model_config = SettingsConfigDict(extra="ignore", nested_delimiter="__")


class AIUsageLedgerSettings(EnvFirstSettings):
    enabled: bool = True
    log_level: str = "INFO"

    model_config = SettingsConfigDict(extra="ignore", nested_delimiter="__")


class AIRouterSettings(EnvFirstSettings):
    local: LocalAISettings = LocalAISettings()
    cloud: CloudAISettings = CloudAISettings()
    usage_ledger: AIUsageLedgerSettings = AIUsageLedgerSettings()

    model_config = SettingsConfigDict(extra="ignore", nested_delimiter="__")


class EmailProviderSettings(EnvFirstSettings):
    enabled: bool = False
    api_key_env: str = ""
    webhook_secret_env: str = ""
    client_id_env: str = ""
    client_secret_env: str = ""
    tenant_id_env: str = ""
    host_env: str = ""
    port_env: str = ""
    username_env: str = ""
    password_env: str = ""
    use_tls_env: str = ""

    model_config = SettingsConfigDict(extra="ignore")


class EmailSettings(EnvFirstSettings):
    default_provider: str = "resend"
    providers: Dict[str, EmailProviderSettings] = {}
    sending_domains: Dict[str, Any] = {}

    model_config = SettingsConfigDict(extra="ignore")


class CampaignQueueSettings(EnvFirstSettings):
    batch_size: int = 50
    throttle_per_second: int = 10
    max_retries: int = 3
    retry_delay_seconds: int = 60


class CampaignSequenceSettings(EnvFirstSettings):
    max_steps: int = 20
    default_interval_days: int = 2


class CampaignSettings(EnvFirstSettings):
    queue: CampaignQueueSettings = CampaignQueueSettings()
    sequence: CampaignSequenceSettings = CampaignSequenceSettings()

    model_config = SettingsConfigDict(extra="ignore")


class CelerySettings(EnvFirstSettings):
    broker_url: str = "redis://localhost:6379/0"
    result_backend: str = "redis://localhost:6379/0"
    task_serializer: str = "json"
    result_serializer: str = "json"
    accept_content: List[str] = ["json"]
    timezone: str = "UTC"
    enable_utc: bool = True
    task_track_started: bool = True
    task_time_limit: int = 3600
    task_soft_time_limit: int = 3000
    worker_prefetch_multiplier: int = 4
    worker_max_tasks_per_child: int = 1000
    beat_schedule: Dict[str, Any] = {}

    # Supports CELERY_BROKER_URL/CELERY_RESULT_BACKEND as well as
    # top-level CELERY__BROKER_URL/CELERY__RESULT_BACKEND.
    model_config = SettingsConfigDict(env_prefix="CELERY_", extra="ignore")


class LoggingSettings(EnvFirstSettings):
    level: str = "INFO"
    format: str = "json"
    output: str = "stdout"
    file_path: Optional[str] = None

    model_config = SettingsConfigDict(env_prefix="LOG_", extra="ignore")


class PackageFeatureSettings(EnvFirstSettings):
    features: Dict[str, bool] = {}
    limits: Dict[str, int] = {}

    model_config = SettingsConfigDict(extra="ignore")


class PackageSettings(EnvFirstSettings):
    STARTER: PackageFeatureSettings = PackageFeatureSettings()
    GROWTH: PackageFeatureSettings = PackageFeatureSettings()
    AI_PRO: PackageFeatureSettings = PackageFeatureSettings()
    ENTERPRISE: PackageFeatureSettings = PackageFeatureSettings()

    model_config = SettingsConfigDict(extra="ignore")


class Settings(EnvFirstSettings):
    """Main settings container loading from YAML + env vars."""

    app: AppSettings = AppSettings()
    database: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    security: SecuritySettings = SecuritySettings()
    firecrawl: FirecrawlSettings = Field(default_factory=FirecrawlSettings)
    google_oauth: GoogleOAuthSettings = GoogleOAuthSettings()
    ai_router: AIRouterSettings = AIRouterSettings()
    email: EmailSettings = EmailSettings()
    campaign: CampaignSettings = CampaignSettings()
    celery: CelerySettings = CelerySettings()
    logging: LoggingSettings = LoggingSettings()
    packages: PackageSettings = PackageSettings()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

    @model_validator(mode="after")
    def validate_production(self):
        from cryptography.fernet import Fernet
        key = self.security.credential_encryption_key
        if key:
            Fernet(key.encode())
            if key == self.security.secret_key:
                raise ValueError("Credential encryption and JWT keys must differ")
        if self.app.environment == "production":
            if self.app.debug or self.database.echo:
                raise ValueError("Production debug and database echo must be disabled")
            if not key:
                raise ValueError("Production requires SECURITY_CREDENTIAL_ENCRYPTION_KEY")
            if any(word in self.security.secret_key.lower() for word in ("change", "example", "your-super")):
                raise ValueError("Production requires a strong JWT secret")
            if self.database.username == "postgres" or self.database.password in ("", "postgres", "password"):
                raise ValueError("Production requires a restricted database role and strong credentials")
            if not self.redis.password:
                raise ValueError("Production requires authenticated Redis")
            if self.celery.accept_content != ["json"]:
                raise ValueError("Only JSON task messages are permitted")
        return self

    @property
    def DATABASE_URL(self) -> str:
        """Flat property for database URL (test compatibility)."""
        return self.database.url

    @property
    def REDIS_URL(self) -> str:
        """Flat property for Redis URL (test compatibility)."""
        return self.redis.url

    @property
    def SECRET_KEY(self) -> str:
        """Flat property for secret key (test compatibility)."""
        return self.security.secret_key

    @property
    def ENVIRONMENT(self) -> str:
        """Flat property for environment (test compatibility)."""
        return self.app.environment

    @classmethod
    def from_yaml(cls, yaml_path: str = "config.yaml") -> "Settings":
        """Load settings from YAML with environment overrides.

        Priority (highest to lowest):
        1. Process environment variables
        2. .env file
        3. YAML config file
        4. Model defaults
        """
        path = Path(yaml_path)
        if not path.exists():
            return cls()

        with open(path, "r") as f:
            yaml_data = yaml.safe_load(f) or {}

        def process_value(v):
            """Convert nested YAML structures without mutating the source mapping."""
            if isinstance(v, dict):
                return {k2: process_value(v2) for k2, v2 in v.items()}
            if isinstance(v, list):
                return [process_value(item) for item in v]
            return v

        kwargs = {key: process_value(value) for key, value in yaml_data.items()}
        return cls(**kwargs)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings.from_yaml()


# Backward-compatible module-level settings object for legacy imports.
# Environment variables are read before application import in normal runtime.
settings = get_settings()
