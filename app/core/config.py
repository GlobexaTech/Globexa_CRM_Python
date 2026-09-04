"""
Configuration management for Globexa CRM.
Uses Pydantic Settings with YAML config file + environment variable overrides.
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from functools import lru_cache

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    name: str = "Globexa CRM"
    version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = []

    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")


class DatabaseSettings(BaseSettings):
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


class RedisSettings(BaseSettings):
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


class FirecrawlSettings(BaseSettings):
    api_key: str = ""
    
    model_config = SettingsConfigDict(env_prefix="FIRECRAWL_", extra="ignore")

    @field_validator("api_key", mode="before")
    @classmethod
    def validate_api_key(cls, v):
        if v is None:
            return ""
        return str(v)


class SecuritySettings(BaseSettings):
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY_MIN_32_CHARS"
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


class GoogleOAuthSettings(BaseSettings):
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    scopes: List[str] = ["openid", "email", "profile"]

    model_config = SettingsConfigDict(env_prefix="GOOGLE_", extra="ignore")

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


class LocalAISettings(BaseSettings):
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


class CloudProviderSettings(BaseSettings):
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


class CloudAISettings(BaseSettings):
    default_provider: str = "nvidia"
    providers: Dict[str, CloudProviderSettings] = {}

    model_config = SettingsConfigDict(extra="ignore", nested_delimiter="__")


class AIUsageLedgerSettings(BaseSettings):
    enabled: bool = True
    log_level: str = "INFO"

    model_config = SettingsConfigDict(extra="ignore", nested_delimiter="__")


class AIRouterSettings(BaseSettings):
    local: LocalAISettings = LocalAISettings()
    cloud: CloudAISettings = CloudAISettings()
    usage_ledger: AIUsageLedgerSettings = AIUsageLedgerSettings()

    model_config = SettingsConfigDict(extra="ignore", nested_delimiter="__")


class EmailProviderSettings(BaseSettings):
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


class EmailSettings(BaseSettings):
    default_provider: str = "resend"
    providers: Dict[str, EmailProviderSettings] = {}
    sending_domains: Dict[str, Any] = {}

    model_config = SettingsConfigDict(extra="ignore")


class CampaignQueueSettings(BaseSettings):
    batch_size: int = 50
    throttle_per_second: int = 10
    max_retries: int = 3
    retry_delay_seconds: int = 60


class CampaignSequenceSettings(BaseSettings):
    max_steps: int = 20
    default_interval_days: int = 2


class CampaignSettings(BaseSettings):
    queue: CampaignQueueSettings = CampaignQueueSettings()
    sequence: CampaignSequenceSettings = CampaignSequenceSettings()

    model_config = SettingsConfigDict(extra="ignore")


class CelerySettings(BaseSettings):
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

    # No env_prefix - use top-level env_nested_delimiter
    model_config = SettingsConfigDict(extra="ignore")


class LoggingSettings(BaseSettings):
    level: str = "INFO"
    format: str = "json"
    output: str = "stdout"
    file_path: Optional[str] = None

    model_config = SettingsConfigDict(env_prefix="LOG_", extra="ignore")


class PackageFeatureSettings(BaseSettings):
    features: Dict[str, bool] = {}
    limits: Dict[str, int] = {}

    model_config = SettingsConfigDict(extra="ignore")


class PackageSettings(BaseSettings):
    STARTER: PackageFeatureSettings = PackageFeatureSettings()
    GROWTH: PackageFeatureSettings = PackageFeatureSettings()
    AI_PRO: PackageFeatureSettings = PackageFeatureSettings()
    ENTERPRISE: PackageFeatureSettings = PackageFeatureSettings()

    model_config = SettingsConfigDict(extra="ignore")


class Settings(BaseSettings):
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

    # Flat properties for backward compatibility with tests
    # FIRECRAWL_API_KEY: Optional[str] = None  # Disabled to avoid nested parsing conflicts

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

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
        """Load settings from YAML file, then override with environment variables.
        
        Priority (highest to lowest):
        1. Environment variables (highest)
        2. YAML config file
        3. Default values (lowest)
        
        We use pydantic-settings' built-in env var support by not passing
        the YAML values as kwargs, but instead temporarily setting them as
        environment variables with a lower priority prefix, then loading settings,
        then restoring the environment.
        """
        import os
        
        path = Path(yaml_path)
        if not path.exists():
            # Return default settings if no config file
            return cls()
        
        with open(path, "r") as f:
            yaml_data = yaml.safe_load(f) or {}
        
        # Flatten YAML to environment variables with a special prefix
        # that won't conflict with actual env vars
        YAML_PREFIX = "_YAML_"
        original_env = {}
        
        def flatten_dict(d: dict, prefix: str = "") -> dict:
            """Flatten nested dict to env var format."""
            result = {}
            for k, v in d.items():
                new_key = f"{prefix}{k.upper()}"
                if isinstance(v, dict):
                    result.update(flatten_dict(v, f"{new_key}__"))
                elif isinstance(v, list):
                    result[new_key] = ",".join(str(item) for item in v)
                else:
                    result[new_key] = str(v)
            return result
        
        # Store original env vars and set YAML values
        flat_yaml = flatten_dict(yaml_data, YAML_PREFIX)
        for key, value in flat_yaml.items():
            if key in os.environ:
                original_env[key] = os.environ[key]
            os.environ[key] = value
        
        try:
            # Now create settings - pydantic will use real env vars (which override YAML)
            # and fall back to our YAML env vars for unset ones
            settings = cls()
            return settings
        finally:
            # Restore original environment
            for key, value in flat_yaml.items():
                if key in original_env:
                    os.environ[key] = original_env[key]
                else:
                    os.environ.pop(key, None)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings.from_yaml()


# Convenience exports - lazy loading to allow env var overrides in tests
# settings = get_settings()