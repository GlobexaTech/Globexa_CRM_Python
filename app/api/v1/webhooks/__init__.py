"""Webhook API module."""
from app.api.v1.webhooks.router import router as webhook_router

__all__ = ["webhook_router"]