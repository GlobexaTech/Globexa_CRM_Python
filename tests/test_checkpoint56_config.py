"""Production fails closed; public Redis and ambiguous credentials cannot boot."""

import copy
import os
import secrets
import socket
from urllib.parse import quote, unquote, urlsplit
import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from app.core.config import Settings, DatabaseSettings, RedisSettings


@pytest.fixture
def production(monkeypatch, tmp_path):
    for key in list(os.environ):
        if key.startswith(("APP_", "DATABASE_", "REDIS_", "SECURITY_", "CELERY_")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    redis_password = secrets.token_urlsafe(32)
    return {
        "app": {
            "environment": "production",
            "debug": False,
            "cors_origins": ["https://crm.example.com"],
        },
        "database": {
            "username": "globexa_runtime",
            "password": secrets.token_urlsafe(32),
            "host": "127.0.0.1",
            "echo": False,
        },
        "redis": {"host": "127.0.0.1", "password": redis_password},
        "security": {
            "secret_key": secrets.token_urlsafe(48),
            "credential_encryption_key": Fernet.generate_key().decode(),
        },
        "celery": {
            "broker_url": f"redis://:{redis_password}@127.0.0.1:6379/0",
            "result_backend": f"redis://:{redis_password}@127.0.0.1:6379/1",
            "task_serializer": "json",
            "result_serializer": "json",
            "accept_content": ["json"],
        },
    }


def test_valid_private_production_configuration(production):
    settings = Settings(**production)
    assert settings.app.environment == "production" and not settings.app.debug
    assert settings.celery.accept_content == ["json"]


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("app", "debug", True),
        ("database", "echo", True),
        ("database", "username", "postgres"),
        ("database", "username", "root"),
        ("database", "password", "postgres"),
        ("database", "password", "password"),
        ("redis", "password", None),
        ("redis", "password", "password"),
        ("redis", "host", "8.8.8.8"),
        ("redis", "host", "0.0.0.0"),
        ("redis", "host", "169.254.169.254"),
        ("redis", "host", "::"),
        ("security", "credential_encryption_key", ""),
        ("security", "secret_key", "CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY"),
        ("security", "secret_key", "a" * 64),
        ("security", "algorithm", "none"),
        ("security", "access_token_expire_minutes", 0),
        ("security", "refresh_token_expire_days", 999),
        ("security", "bcrypt_rounds", 4),
        ("app", "cors_origins", ["*"]),
        ("app", "cors_origins", ["https://*.example.com"]),
        ("app", "cors_origins", ["http://crm.example.com"]),
        ("app", "cors_origins", ["https://user:pass@crm.example.com"]),
        ("app", "cors_origins", ["https://crm.example.com/path"]),
        ("app", "cors_origins", ["https://crm.example.com?unsafe=true"]),
        ("celery", "accept_content", ["json", "pickle"]),
        ("celery", "task_serializer", "pickle"),
        ("celery", "result_serializer", "yaml"),
        ("celery", "broker_url", "redis://127.0.0.1:6379/0"),
        ("celery", "result_backend", "redis://127.0.0.1:6379/0"),
        ("celery", "broker_url", "amqp://guest:guest@127.0.0.1:5672/"),
    ],
)
def test_unsafe_production_configuration_rejected(production, section, key, value):
    data = copy.deepcopy(production)
    data[section][key] = value
    with pytest.raises((ValidationError, ValueError)):
        Settings(**data)


@pytest.mark.parametrize("field", ["broker_url", "result_backend"])
def test_celery_private_authenticated_endpoint_required(production, field):
    password = secrets.token_urlsafe(32)
    for endpoint in [
        f"redis://:{password}@8.8.8.8:6379/0",
        f"redis://:{password}@169.254.169.254:6379/0",
        f"rediss://:{password}@127.0.0.1:6379/0?ssl_cert_reqs=none",
        f"rediss://:{password}@127.0.0.1:6379/0?ssl_cert_reqs=",
        f"redis://:{password}@127.0.0.1:6379/0?password=override",
    ]:
        data = copy.deepcopy(production)
        data["celery"][field] = endpoint
        with pytest.raises(ValidationError):
            Settings(**data)


def test_private_dns_must_resolve_exclusively_private(production, monkeypatch):
    production["redis"]["host"] = "redis.internal"
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 6379))],
    )
    assert Settings(**production).redis.host == "redis.internal"
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 6379)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 6379)),
        ],
    )
    with pytest.raises(ValidationError):
        Settings(**production)


def test_production_environment_case_cannot_skip_validation(production):
    production["app"]["environment"] = " PRODUCTION "
    production["app"]["debug"] = True
    with pytest.raises(ValidationError):
        Settings(**production)


def test_db_and_redis_credentials_are_percent_escaped(production):
    password = secrets.token_urlsafe(20) + "@:/?#% plus"
    database = DatabaseSettings(
        username="globexa@runtime", password=password, host="::1", name="globexa_test"
    )
    assert make_url(database.url).password == password
    assert make_url(database.sync_url).username == "globexa@runtime"
    assert make_url(database.url).host == "::1"
    redis = RedisSettings(host="::1", password=password)
    parsed = urlsplit(redis.url)
    assert unquote(parsed.password) == password and parsed.hostname == "::1"
    assert quote(password, safe="") in redis.url


def test_production_error_does_not_echo_credentials(production):
    secret = production["database"]["password"]
    production["app"]["debug"] = True
    with pytest.raises(ValidationError) as exc:
        Settings(**production)
    assert secret not in str(exc.value)
