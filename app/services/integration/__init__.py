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
from app.services.integration.firecrawl_adapter import FirecrawlAdapter

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
    "FirecrawlAdapter",
]