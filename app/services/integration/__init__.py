"""
Integration services package.
"""
from app.services.integration.adapter import (
    IntegrationAdapter,
    LeadData,
    SyncResult,
    IntegrationAdapterFactory,
    IntegrationService,
    MetaAdapter,
    GoogleAdsAdapter,
    LinkedInAdapter,
    ApolloAdapter,
    CSVAdapter,
    WebhookAdapter,
    EmailInboxAdapter,
)

__all__ = [
    "IntegrationAdapter",
    "LeadData",
    "SyncResult",
    "IntegrationAdapterFactory",
    "IntegrationService",
    "MetaAdapter",
    "GoogleAdsAdapter",
    "LinkedInAdapter",
    "ApolloAdapter",
    "CSVAdapter",
    "WebhookAdapter",
    "EmailInboxAdapter",
]