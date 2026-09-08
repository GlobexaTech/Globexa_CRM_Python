"""Narrow signed unsubscribe capability; never grants CRM read access."""

import os
from datetime import timedelta
import jwt
from fastapi import HTTPException
from app.core.config import get_settings
from app.services.crm.common import now


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
