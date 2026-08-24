"""
Email services package.
"""
from app.services.email.provider import (
    EmailProvider,
    EmailProviderType,
    EmailMessage,
    EmailResult,
    ProviderConfig,
    ResendProvider,
    GmailProvider,
    MicrosoftProvider,
    SMTPProvider,
    EmailProviderFactory,
    EmailService,
)

__all__ = [
    "EmailProvider",
    "EmailProviderType",
    "EmailMessage",
    "EmailResult",
    "ProviderConfig",
    "ResendProvider",
    "GmailProvider",
    "MicrosoftProvider",
    "SMTPProvider",
    "EmailProviderFactory",
    "EmailService",
]