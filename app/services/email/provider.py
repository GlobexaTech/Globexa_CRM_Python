"""
Email Provider Abstraction for Globexa CRM.
Base interface and adapters for Resend, Gmail, Microsoft Graph, SMTP.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum
import httpx
import structlog
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib

logger = structlog.get_logger()


class EmailProviderType(str, Enum):
    RESEND = "resend"
    GMAIL = "gmail"
    MICROSOFT = "microsoft"
    SMTP = "smtp"


@dataclass
class EmailMessage:
    """Standardized email message."""
    to: List[str]
    subject: str
    html_content: str
    text_content: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    tags: Optional[List[str]] = None
    track_opens: bool = True
    track_clicks: bool = True


@dataclass
class EmailResult:
    """Standardized email send result."""
    success: bool
    message_id: Optional[str] = None
    provider: str = ""
    error_message: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class ProviderConfig:
    """Provider configuration."""
    provider_type: EmailProviderType
    credentials: Dict[str, Any]
    settings: Optional[Dict[str, Any]] = None


class EmailProvider(ABC):
    """Abstract base class for email providers."""

    @property
    @abstractmethod
    def provider_type(self) -> EmailProviderType:
        pass

    @abstractmethod
    async def send(self, message: EmailMessage, config: ProviderConfig) -> EmailResult:
        """Send an email."""
        pass

    @abstractmethod
    async def verify_domain(self, domain: str, config: ProviderConfig) -> Dict[str, Any]:
        """Verify domain ownership (DKIM, SPF, DMARC)."""
        pass

    @abstractmethod
    async def get_webhook_events(self, payload: Dict[str, Any], config: ProviderConfig) -> List[Dict[str, Any]]:
        """Parse webhook events into standardized format."""
        pass

    @abstractmethod
    async def suppress_email(self, email: str, config: ProviderConfig) -> bool:
        """Add email to suppression list."""
        pass


class ResendProvider(EmailProvider):
    """Resend.com email provider."""

    @property
    def provider_type(self) -> EmailProviderType:
        return EmailProviderType.RESEND

    async def send(self, message: EmailMessage, config: ProviderConfig) -> EmailResult:
        api_key = config.credentials.get("api_key")
        if not api_key:
            return EmailResult(success=False, error_message="Missing API key", provider=self.provider_type.value)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "from": f"{message.from_name} <{message.from_email}>" if message.from_name else message.from_email,
            "to": message.to,
            "subject": message.subject,
            "html": message.html_content,
            "text": message.text_content,
            "reply_to": message.reply_to,
            "tags": [{"name": tag, "value": "true"} for tag in (message.tags or [])],
        }

        # Add tracking headers
        if message.track_opens:
            payload["headers"] = {"X-Track-Opens": "true"}
        if message.track_clicks:
            payload.setdefault("headers", {})["X-Track-Clicks"] = "true"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return EmailResult(
                    success=True,
                    message_id=data.get("id"),
                    provider=self.provider_type.value,
                    raw_response=data,
                )
        except httpx.HTTPStatusError as e:
            logger.error("Resend send failed", status=e.response.status_code, error=e.response.text)
            return EmailResult(
                success=False,
                error_message=f"Resend error: {e.response.text}",
                provider=self.provider_type.value,
            )
        except Exception as e:
            logger.error("Resend send exception", error=str(e))
            return EmailResult(
                success=False,
                error_message=str(e),
                provider=self.provider_type.value,
            )

    async def verify_domain(self, domain: str, config: ProviderConfig) -> Dict[str, Any]:
        api_key = config.credentials.get("api_key")
        headers = {"Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get domain info
            response = await client.get(f"https://api.resend.com/domains/{domain}", headers=headers)
            if response.status_code == 404:
                # Create domain
                response = await client.post(
                    "https://api.resend.com/domains",
                    headers=headers,
                    json={"name": domain},
                )
            response.raise_for_status()
            return response.json()

    async def get_webhook_events(self, payload: Dict[str, Any], config: ProviderConfig) -> List[Dict[str, Any]]:
        """Parse Resend webhook events."""
        events = []
        event_type = payload.get("type", "")

        # Resend sends single event per webhook
        data = payload.get("data", {})
        events.append({
            "provider_event_id": payload.get("id", ""),
            "provider_event_type": event_type,
            "event_data": data,
            "recipient_email": data.get("to", [None])[0] if data.get("to") else None,
            "provider_message_id": data.get("email_id"),
        })
        return events

    async def suppress_email(self, email: str, config: ProviderConfig) -> bool:
        api_key = config.credentials.get("api_key")
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.resend.com/suppressions",
                    headers=headers,
                    json={"email": email},
                )
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error("Resend suppress failed", email=email, error=str(e))
            return False


class GmailProvider(EmailProvider):
    """Gmail/Google Workspace provider via Gmail API."""

    @property
    def provider_type(self) -> EmailProviderType:
        return EmailProviderType.GMAIL

    async def _get_access_token(self, config: ProviderConfig) -> str:
        """Get valid access token, refreshing if needed."""
        # This would use the stored refresh token to get a new access token
        # Implementation depends on how tokens are stored
        credentials = config.credentials
        return credentials.get("access_token", "")

    async def send(self, message: EmailMessage, config: ProviderConfig) -> EmailResult:
        access_token = await self._get_access_token(config)
        if not access_token:
            return EmailResult(success=False, error_message="No access token", provider=self.provider_type.value)

        # Build MIME message
        mime_message = MIMEMultipart("alternative")
        mime_message["To"] = ", ".join(message.to)
        mime_message["Subject"] = message.subject
        mime_message["From"] = f"{message.from_name} <{message.from_email}>" if message.from_name else message.from_email
        if message.reply_to:
            mime_message["Reply-To"] = message.reply_to

        if message.text_content:
            mime_message.attach(MIMEText(message.text_content, "plain"))
        mime_message.attach(MIMEText(message.html_content, "html"))

        # Encode for Gmail API
        import base64
        raw_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                    headers=headers,
                    json={"raw": raw_message},
                )
                response.raise_for_status()
                data = response.json()
                return EmailResult(
                    success=True,
                    message_id=data.get("id"),
                    provider=self.provider_type.value,
                    raw_response=data,
                )
        except httpx.HTTPStatusError as e:
            logger.error("Gmail send failed", status=e.response.status_code, error=e.response.text)
            return EmailResult(
                success=False,
                error_message=f"Gmail error: {e.response.text}",
                provider=self.provider_type.value,
            )
        except Exception as e:
            logger.error("Gmail send exception", error=str(e))
            return EmailResult(
                success=False,
                error_message=str(e),
                provider=self.provider_type.value,
            )

    async def verify_domain(self, domain: str, config: ProviderConfig) -> Dict[str, Any]:
        # Gmail doesn't have domain verification in the same way
        # This would check if the domain is verified in Google Workspace
        return {"domain": domain, "verified": True, "note": "Uses Google Workspace domain"}

    async def get_webhook_events(self, payload: Dict[str, Any], config: ProviderConfig) -> List[Dict[str, Any]]:
        # Gmail uses Pub/Sub push, not direct webhooks
        # This would parse the Pub/Sub message
        events = []
        message = payload.get("message", {})
        data = message.get("data", "")
        if data:
            import base64
            import json
            decoded = base64.b64decode(data).decode()
            gmail_data = json.loads(decoded)
            events.append({
                "provider_event_id": gmail_data.get("historyId", ""),
                "provider_event_type": "gmail_notification",
                "event_data": gmail_data,
                "recipient_email": None,
                "provider_message_id": None,
            })
        return events

    async def suppress_email(self, email: str, config: ProviderConfig) -> bool:
        # Gmail doesn't have a suppression API
        return True


class MicrosoftProvider(EmailProvider):
    """Microsoft Graph (Outlook/Exchange) provider."""

    @property
    def provider_type(self) -> EmailProviderType:
        return EmailProviderType.MICROSOFT

    async def _get_access_token(self, config: ProviderConfig) -> str:
        """Get valid access token using client credentials flow."""
        credentials = config.credentials
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        tenant_id = credentials.get("tenant_id")

        if not all([client_id, client_secret, tenant_id]):
            return ""

        # Use cached token if available and not expired
        cached_token = credentials.get("access_token")
        expires_at = credentials.get("expires_at", 0)
        import time
        if cached_token and expires_at > time.time() + 60:
            return cached_token

        # Get new token
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(token_url, data=data)
            response.raise_for_status()
            token_data = response.json()
            access_token = token_data["access_token"]
            expires_in = token_data["expires_in"]

            # Update cache (in production, persist this)
            import time
            credentials["access_token"] = access_token
            credentials["expires_at"] = time.time() + expires_in

            return access_token

    async def send(self, message: EmailMessage, config: ProviderConfig) -> EmailResult:
        access_token = await self._get_access_token(config)
        if not access_token:
            return EmailResult(success=False, error_message="No access token", provider=self.provider_type.value)

        # Build message for Microsoft Graph
        payload = {
            "message": {
                "subject": message.subject,
                "body": {
                    "contentType": "HTML",
                    "content": message.html_content,
                },
                "toRecipients": [{"emailAddress": {"address": addr}} for addr in message.to],
                "from": {
                    "emailAddress": {
                        "address": message.from_email,
                        "name": message.from_name or "",
                    }
                },
            },
            "saveToSentItems": "true",
        }

        if message.text_content:
            payload["message"]["body"]["contentType"] = "HTML"
            # Could add text alternative

        if message.reply_to:
            payload["message"]["replyTo"] = [{"emailAddress": {"address": message.reply_to}}]

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://graph.microsoft.com/v1.0/users/me/sendMail",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                # Microsoft Graph returns 202 Accepted with no body on success
                return EmailResult(
                    success=True,
                    message_id=response.headers.get("Location", "").split("/")[-1] if response.headers.get("Location") else None,
                    provider=self.provider_type.value,
                    raw_response={"status": "sent"},
                )
        except httpx.HTTPStatusError as e:
            logger.error("Microsoft Graph send failed", status=e.response.status_code, error=e.response.text)
            return EmailResult(
                success=False,
                error_message=f"Microsoft Graph error: {e.response.text}",
                provider=self.provider_type.value,
            )
        except Exception as e:
            logger.error("Microsoft Graph send exception", error=str(e))
            return EmailResult(
                success=False,
                error_message=str(e),
                provider=self.provider_type.value,
            )

    async def verify_domain(self, domain: str, config: ProviderConfig) -> Dict[str, Any]:
        # Check domain in Azure AD / Microsoft 365
        access_token = await self._get_access_token(config)
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://graph.microsoft.com/v1.0/domains/{domain}",
                headers=headers,
            )
            if response.status_code == 404:
                return {"domain": domain, "verified": False}
            response.raise_for_status()
            data = response.json()
            return {"domain": domain, "verified": data.get("isVerified", False), "details": data}

    async def get_webhook_events(self, payload: Dict[str, Any], config: ProviderConfig) -> List[Dict[str, Any]]:
        # Microsoft Graph uses webhook subscriptions
        events = []
        for change in payload.get("value", []):
            resource_data = change.get("resourceData", {})
            events.append({
                "provider_event_id": change.get("subscriptionId", ""),
                "provider_event_type": change.get("changeType", ""),
                "event_data": resource_data,
                "recipient_email": resource_data.get("toRecipients", [{}])[0].get("emailAddress", {}).get("address"),
                "provider_message_id": resource_data.get("id"),
            })
        return events

    async def suppress_email(self, email: str, config: ProviderConfig) -> bool:
        # Microsoft doesn't have a direct suppression API
        return True


class SMTPProvider(EmailProvider):
    """Generic SMTP provider."""

    @property
    def provider_type(self) -> EmailProviderType:
        return EmailProviderType.SMTP

    async def send(self, message: EmailMessage, config: ProviderConfig) -> EmailResult:
        credentials = config.credentials
        host = credentials.get("host")
        port = credentials.get("port", 587)
        username = credentials.get("username")
        password = credentials.get("password")
        use_tls = credentials.get("use_tls", True)

        if not all([host, username, password]):
            return EmailResult(success=False, error_message="Missing SMTP credentials", provider=self.provider_type.value)

        # Build MIME message
        mime_message = MIMEMultipart("alternative")
        mime_message["To"] = ", ".join(message.to)
        mime_message["Subject"] = message.subject
        mime_message["From"] = f"{message.from_name} <{message.from_email}>" if message.from_name else message.from_email
        if message.reply_to:
            mime_message["Reply-To"] = message.reply_to

        if message.text_content:
            mime_message.attach(MIMEText(message.text_content, "plain"))
        mime_message.attach(MIMEText(message.html_content, "html"))

        try:
            await aiosmtplib.send(
                mime_message,
                hostname=host,
                port=port,
                username=username,
                password=password,
                use_tls=use_tls,
            )
            return EmailResult(
                success=True,
                message_id=None,  # SMTP doesn't return message ID easily
                provider=self.provider_type.value,
                raw_response={"status": "sent"},
            )
        except Exception as e:
            logger.error("SMTP send failed", error=str(e))
            return EmailResult(
                success=False,
                error_message=f"SMTP error: {str(e)}",
                provider=self.provider_type.value,
            )

    async def verify_domain(self, domain: str, config: ProviderConfig) -> Dict[str, Any]:
        # SMTP doesn't have domain verification
        return {"domain": domain, "verified": True, "note": "SMTP - manual verification required"}

    async def get_webhook_events(self, payload: Dict[str, Any], config: ProviderConfig) -> List[Dict[str, Any]]:
        # SMTP doesn't have webhooks
        return []

    async def suppress_email(self, email: str, config: ProviderConfig) -> bool:
        # SMTP doesn't have suppression API
        return True


class EmailProviderFactory:
    """Factory for creating email provider instances."""

    _providers = {
        EmailProviderType.RESEND: ResendProvider,
        EmailProviderType.GMAIL: GmailProvider,
        EmailProviderType.MICROSOFT: MicrosoftProvider,
        EmailProviderType.SMTP: SMTPProvider,
    }

    @classmethod
    def get_provider(cls, provider_type: EmailProviderType) -> EmailProvider:
        provider_class = cls._providers.get(provider_type)
        if not provider_class:
            raise ValueError(f"Unknown provider type: {provider_type}")
        return provider_class()

    @classmethod
    def register_provider(cls, provider_type: EmailProviderType, provider_class: type):
        cls._providers[provider_type] = provider_class


class EmailService:
    """High-level email service using provider abstraction."""

    def __init__(self):
        self.factory = EmailProviderFactory()

    async def send_email(
        self,
        message: EmailMessage,
        provider_type: EmailProviderType,
        config: ProviderConfig,
    ) -> EmailResult:
        """Send email via specified provider."""
        provider = self.factory.get_provider(provider_type)
        return await provider.send(message, config)

    async def send_bulk(
        self,
        messages: List[EmailMessage],
        provider_type: EmailProviderType,
        config: ProviderConfig,
        batch_size: int = 50,
        delay_seconds: float = 0.1,
    ) -> List[EmailResult]:
        """Send multiple emails with throttling."""
        provider = self.factory.get_provider(provider_type)
        results = []

        for i, message in enumerate(messages):
            result = await provider.send(message, config)
            results.append(result)

            # Throttle
            if i < len(messages) - 1:
                import asyncio
                await asyncio.sleep(delay_seconds)

        return results

    async def verify_domain(
        self,
        domain: str,
        provider_type: EmailProviderType,
        config: ProviderConfig,
    ) -> Dict[str, Any]:
        """Verify domain for a provider."""
        provider = self.factory.get_provider(provider_type)
        return await provider.verify_domain(domain, config)

    async def process_webhook(
        self,
        provider_type: EmailProviderType,
        payload: Dict[str, Any],
        config: ProviderConfig,
    ) -> List[Dict[str, Any]]:
        """Process webhook events from provider."""
        provider = self.factory.get_provider(provider_type)
        return await provider.get_webhook_events(payload, config)

    async def add_suppression(
        self,
        email: str,
        provider_type: EmailProviderType,
        config: ProviderConfig,
    ) -> bool:
        """Add email to suppression list."""
        provider = self.factory.get_provider(provider_type)
        return await provider.suppress_email(email, config)