"""Reject protected fields before mutable-dictionary endpoints execute."""
from fastapi import HTTPException, Request

PROTECTED = {"id", "tenant_id", "user_id", "is_superuser", "permissions", "hashed_password",
             "created_at", "updated_at", "created_by_id", "updated_by_id", "invited_by_id",
             "email_verified", "google_id", "credentials_encrypted"}
SECRET_KEYS = {"password", "secret", "api_key", "access_token", "refresh_token", "client_secret",
               "authorization", "webhook_secret", "credentials", "provider_credentials"}


def is_secret_key(key):
    normalized = str(key).lower().replace("_", "").replace("-", "")
    return normalized in {item.replace("_", "") for item in SECRET_KEYS}


def contains_secrets(value):
    if isinstance(value, dict):
        return any(is_secret_key(key) or contains_secrets(item) for key, item in value.items())
    if isinstance(value, list):
        return any(contains_secrets(item) for item in value)
    return False


def redact(value):
    if isinstance(value, dict):
        return {key: "[redacted]" if is_secret_key(key) else redact(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


async def protect_input(request: Request):
    if request.method not in {"POST", "PUT", "PATCH"}:
        return
    if request.url.path.startswith("/api/v1/hooks/"):
        return
    if "application/json" not in request.headers.get("content-type", ""):
        return
    try:
        value = await request.json()
    except ValueError:
        return
    if not isinstance(value, dict):
        return
    protected = PROTECTED.intersection(value)
    if "role" in value and "/users" not in request.url.path:
        protected.add("role")
    if protected:
        raise HTTPException(422, "Protected fields cannot be supplied")
    for key in ("config", "custom_fields", "settings", "metadata", "provider_config", "arguments", "condition"):
        if contains_secrets(value.get(key)):
            raise HTTPException(422, "Store secrets through the credential service")
