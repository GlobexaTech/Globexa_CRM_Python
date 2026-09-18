"""Narrow signed unsubscribe capability; never grants CRM read access."""

import os
from datetime import timedelta
import jwt
from uuid import UUID
from fastapi import HTTPException
from app.core.config import get_settings
from app.services.crm.common import now


def decode_unsubscribe_token(token):
    """Validate only the narrow email-preference capability, never an auth JWT."""
    settings = get_settings().security
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm],
                             options={"require": ["exp", "sub", "tenant_id", "type"]})
        if payload["type"] != "unsubscribe":
            return None
        UUID(payload["sub"])
        UUID(payload["tenant_id"])
        return payload
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
        return None


def unsubscribe_url(tenant_id, contact_id):
    base = os.environ.get("CRM_PUBLIC_BASE_URL", "").rstrip("/")
    if not base.startswith("https://"):
        raise HTTPException(
            409,
            "Configure CRM_PUBLIC_BASE_URL for unsubscribe links before launching campaigns",
        )
    settings = get_settings().security
    token = jwt.encode(
        {
            "sub": str(contact_id),
            "tenant_id": str(tenant_id),
            "type": "unsubscribe",
            "exp": now() + timedelta(days=180),
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    return base + "/api/v1/unsubscribe?token=" + token
