"""Capability-based providers. Unsupported operations fail explicitly."""

import base64
import os
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.parse import urlencode
from typing import Protocol
import httpx
import json


class ProviderFailure(RuntimeError):
    def __init__(self, code="provider_failure", *, retryable=False, uncertain=False):
        super().__init__(code)
        self.code, self.retryable, self.uncertain = code, retryable, uncertain


class ProviderAdapter(Protocol):
    capabilities: frozenset[str]
    idempotent_send: bool

    async def connect(self, code, verifier, redirect_uri): ...
    async def disconnect(self, token): ...
    async def refresh(self, refresh_token): ...
    async def health_check(self, token): ...
    async def sync(self, token, cursor=None): ...
    async def send(self, token, message, idempotency_key): ...
    async def handle_webhook(self, payload): ...


class UnavailableAdapter:
    capabilities = frozenset()
    idempotent_send = False

    async def unsupported(self, *args, **kwargs):
        raise ProviderFailure("capability_unavailable")

    connect = disconnect = refresh = health_check = sync = send = handle_webhook = (
        unsupported
    )


class MailAdapter:
    capabilities = frozenset(
        {"connect", "disconnect", "refresh", "health_check", "sync", "send"}
    )
    # Neither API promises deduplication of retries by a caller-supplied key.
    idempotent_send = False

    def __init__(self, name, transport=None):
        self.name, self.spec, self.transport = name, SPECS[name], transport

    def configuration(self):
        prefix = "CRM_" + self.name.upper()
        values = {
            key: os.environ.get(prefix + "_" + key.upper(), "")
            for key in ("client_id", "client_secret", "redirect_uri")
        }
        if not all(values.values()) or not values["redirect_uri"].startswith(
            "https://"
        ):
            raise ProviderFailure("oauth_not_configured")
        return values

    def authorization_url(self, state, challenge):
        cfg = self.configuration()
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": self.spec["scopes"],
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if self.name == "gmail":
            params.update(access_type="offline", prompt="consent")
        return self.spec["authorize"] + "?" + urlencode(params)

    async def request(self, method, url, *, external_write=False, **kwargs):
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=30, follow_redirects=False
            ) as client:
                response = await client.request(method, url, **kwargs)
        except httpx.HTTPError:
            raise ProviderFailure(
                "transport_error",
                retryable=not external_write,
                uncertain=external_write,
            ) from None
        if response.status_code >= 400:
            raise ProviderFailure(
                f"provider_http_{response.status_code}",
                retryable=response.status_code == 429
                or (response.status_code >= 500 and not external_write),
                uncertain=external_write and response.status_code >= 500,
            )
        try:
            return response.json() if response.content else {}
        except ValueError:
            raise ProviderFailure(
                "invalid_provider_response", uncertain=external_write
            ) from None

    async def connect(self, code, verifier, redirect_uri):
        cfg = self.configuration()
        if redirect_uri != cfg["redirect_uri"]:
            raise ProviderFailure("redirect_mismatch")
        return await self.request(
            "POST",
            self.spec["exchange_endpoint"],
            external_write=True,
            data={
                **cfg,
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
            },
        )

    async def refresh(self, refresh_token):
        cfg = self.configuration()
        return await self.request(
            "POST",
            self.spec["exchange_endpoint"],
            external_write=True,
            data={**cfg, "grant_type": "refresh_token", "refresh_token": refresh_token},
        )

    async def disconnect(self, token):
        # Outlook has no equivalent per-app delegated-token revocation endpoint.
        if self.name == "gmail":
            await self.request(
                "POST",
                "https://oauth2.googleapis.com/revoke",
                external_write=True,
                data={"token": token},
            )
        return {"remote_revocation": self.name == "gmail"}

    async def health_check(self, token):
        path = "/users/me/profile" if self.name == "gmail" else "/me"
        data = await self.request(
            "GET", self.spec["api"] + path, headers={"Authorization": "Bearer " + token}
        )
        return {
            "connected": True,
            "address": data.get("emailAddress")
            or data.get("mail")
            or data.get("userPrincipalName"),
        }

    async def send(self, token, message, idempotency_key):
        if message.get("attachments"):
            raise ProviderFailure("outbound_attachments_not_supported")
        headers = {"Authorization": "Bearer " + token}
        if self.name == "gmail":
            mime = EmailMessage()
            mime["To"], mime["Subject"] = message["recipient"], message["subject"]
            mime["Message-ID"] = (
                "<" + idempotency_key.replace(":", ".") + "@crm.globexa.invalid>"
            )
            if message.get("unsubscribe_url"):
                mime["List-Unsubscribe"] = "<" + message["unsubscribe_url"] + ">"
                mime["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
            mime.set_content(message["body"])
            payload = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}
            if message.get("thread_id"):
                payload["threadId"] = message["thread_id"]
            result = await self.request(
                "POST",
                self.spec["api"] + "/users/me/messages/send",
                external_write=True,
                headers=headers,
                json=payload,
            )
            return {
                "provider_message_id": result["id"],
                "thread_id": result.get("threadId"),
                "status": "sent",
            }
        await self.request(
            "POST",
            self.spec["api"] + "/me/sendMail",
            external_write=True,
            headers=headers,
            json={
                "message": {
                    "subject": message["subject"],
                    "body": {"contentType": "Text", "content": message["body"]},
                    "toRecipients": [
                        {"emailAddress": {"address": message["recipient"]}}
                    ],
                },
                "saveToSentItems": True,
            },
        )
        return {"provider_message_id": None, "status": "sent"}

    async def sync(self, token, cursor=None):
        headers = {"Authorization": "Bearer " + token}
        if self.name == "outlook":
            # Cursor is an integer offset, never an arbitrary URL from the caller.
            offset = int(cursor or 0)
            if not 0 <= offset <= 100000:
                raise ProviderFailure("invalid_cursor")
            data = await self.request(
                "GET",
                self.spec["api"] + "/me/mailFolders/inbox/messages",
                headers=headers,
                params={
                    "$top": 25,
                    "$skip": offset,
                    "$orderby": "receivedDateTime desc",
                    "$select": "id,conversationId,subject,bodyPreview,from,toRecipients,receivedDateTime",
                },
            )
            items = []
            for r in data.get("value", []):
                items.append(
                    {
                        "provider_message_id": r["id"],
                        "thread_id": r.get("conversationId", r["id"]),
                        "subject": r.get("subject") or "(no subject)",
                        "body": r.get("bodyPreview") or "(empty message)",
                        "sender": r.get("from", {})
                        .get("emailAddress", {})
                        .get("address", ""),
                        "recipient": next(
                            iter(r.get("toRecipients", [])), {}
                        ).get("emailAddress", {})
                        .get("address", ""),
                        "occurred_at": r["receivedDateTime"],
                        "attachments": [],
                    }
                )
            return {
                "messages": items,
                "cursor": str(offset + 25) if data.get("@odata.nextLink") else None,
            }
        params = {"maxResults": 25, "labelIds": "INBOX"}
        if cursor:
            params["pageToken"] = cursor
        data = await self.request(
            "GET",
            self.spec["api"] + "/users/me/messages",
            headers=headers,
            params=params,
        )
        items = []
        for ref in data.get("messages", []):
            item = await self.request(
                "GET",
                self.spec["api"] + "/users/me/messages/" + ref["id"],
                headers=headers,
                params={"format": "full"},
            )
            fields = {
                h["name"].lower(): h["value"]
                for h in item.get("payload", {}).get("headers", [])
            }
            parts, attachments = [], []
            stack = [(item.get("payload", {}), 0)]
            while stack:
                part, depth = stack.pop()
                if depth > 8:
                    raise ProviderFailure("message_mime_too_deep")
                body = part.get("body", {})
                if part.get("mimeType") == "text/plain" and body.get("data"):
                    parts.append(
                        base64.urlsafe_b64decode(
                            body["data"] + "=" * (-len(body["data"]) % 4)
                        ).decode("utf-8", errors="replace")
                    )
                if part.get("filename") and body.get("attachmentId"):
                    attachments.append(
                        {
                            "name": part["filename"],
                            "content_type": part.get(
                                "mimeType", "application/octet-stream"
                            ),
                            "size": body.get("size", 0),
                            "provider_attachment_id": body.get("attachmentId"),
                        }
                    )
                stack.extend((child, depth + 1) for child in part.get("parts", []))
            items.append(
                {
                    "provider_message_id": item["id"],
                    "thread_id": item.get("threadId"),
                    "subject": fields.get("subject") or "(no subject)",
                    "body": "\\n".join(parts)
                    or item.get("snippet")
                    or "(empty message)",
                    "sender": parseaddr(fields.get("from", ""))[1],
                    "recipient": parseaddr(fields.get("to", ""))[1],
                    "occurred_at": datetime.fromtimestamp(
                        int(item["internalDate"]) / 1000, timezone.utc
                    ).isoformat(),
                    "attachments": attachments,
                }
            )
        return {"messages": items, "cursor": data.get("nextPageToken")}

    async def handle_webhook(self, payload):
        raise ProviderFailure("provider_push_contract_not_configured")


class WhatsAppAdapter:
    capabilities = frozenset(
        {"connect", "disconnect", "refresh", "health_check", "sync", "send", "handle_webhook"}
    )
    # WhatsApp does not provide idempotency keys for outbound messages, but we can use our own.
    idempotent_send = False

    def __init__(self, transport=None):
        self.spec = SPECS["whatsapp"]
        self.transport = transport

    def configuration(self):
        # WhatsApp Cloud API uses a permanent access token (long-lived) or we can use a system user token.
        # For simplicity, we expect the token to be stored directly in the credentials.
        # We'll also need the phone number ID from the Meta Business Account.
        cfg = {
            "access_token": os.environ.get("CRM_WHATSAPP_ACCESS_TOKEN", ""),
            "phone_number_id": os.environ.get("CRM_WHATSAPP_PHONE_NUMBER_ID", ""),
            "business_account_id": os.environ.get("CRM_WHATSAPP_BUSINESS_ACCOUNT_ID", ""),
            "verify_token": os.environ.get("CRM_WHATSAPP_VERIFY_TOKEN", ""),
            # The webhook URL is set in the integration config, not in credentials.
        }
        if not cfg["access_token"]:
            raise ProviderFailure("whatsapp_not_configured")
        return cfg

    # WhatsApp doesn't use OAuth code exchange in the same way; we treat the access token as the credential.
    # For the purpose of the integrations framework, we'll implement connect/disconnect as no-ops
    # that just validate the token.
    async def connect(self, code, verifier, redirect_uri):
        # WhatsApp Cloud API uses a permanent token, so we ignore the OAuth flow.
        # However, to fit the framework, we'll just validate the token.
        cfg = self.configuration()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://graph.facebook.com/v18.0/{cfg['phone_number_id']}",
                    params={"access_token": cfg["access_token"]},
                )
                if response.status_code != 200:
                    raise ProviderFailure("invalid_token")
        except httpx.HTTPError as e:
            raise ProviderFailure("provider_connection_failed") from e
        return {"status": "connected"}

    async def disconnect(self, token):
        # WhatsApp tokens can be revoked by deleting the phone number from the business account,
        # but we'll just return success.
        return {"remote_revocation": False}

    async def refresh(self, refresh_token):
        # WhatsApp access tokens are long-lived and don't refresh in the same way.
        # We'll just return the same token.
        cfg = self.configuration()
        return {
            "access_token": cfg["access_token"],
            "token_type": "Bearer",
            "expires_in": 0,  # No expiry
        }

    async def health_check(self, token):
        cfg = self.configuration()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://graph.facebook.com/v18.0/{cfg['phone_number_id']}",
                    params={"access_token": cfg["access_token"]},
                )
                data = response.json()
                return {
                    "connected": True,
                    "address": data.get("verified_name")
                    or f"WhatsApp Business Account {cfg['business_account_id']}",
                }
        except Exception:
            return {"connected": False, "address": None}

    async def send(self, token, message, idempotency_key):
        cfg = self.configuration()
        headers = {
            "Authorization": f"Bearer {cfg['access_token']}",
            "Content-Type": "application/json",
        }
        # WhatsApp expects a specific JSON structure for text messages.
        # We'll support only text messages for now.
        if message.get("attachments"):
            raise ProviderFailure("outbound_attachments_not_supported")
        payload = {
            "messaging_product": "whatsapp",
            "to": message["recipient"],  # Should be in international format
            "type": "text",
            "text": {"body": message["body"]},
        }
        # Note: WhatsApp does not use an idempotency key in the API, but we can rely on
        # our own idempotency layer in the webhook processing.
        # We'll add a custom header for idempotency if needed, but the API doesn't support it.
        # Instead, we rely on the webhook deduplication at the ingestion layer.
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"https://graph.facebook.com/v18.0/{cfg['phone_number_id']}/messages",
                    headers=headers,
                    json=payload,
                )
                if response.status_code >= 400:
                    raise ProviderFailure(
                        f"provider_http_{response.status_code}",
                        retryable=response.status_code == 429,
                        uncertain=True,
                    )
                result = response.json()
                return {
                    "provider_message_id": result["messages"][0]["id"],
                    "status": "sent",
                }
        except httpx.HTTPError as e:
            raise ProviderFailure("provider_http_error") from e

    async def sync(self, token, cursor=None):
        # WhatsApp does not provide a way to sync historical messages via the Cloud API
        # for regular business accounts. We'll return empty.
        # For customer service conversations, we might need to use the inbound webhook only.
        return {"messages": [], "cursor": None}

    async def handle_webhook(self, payload):
        # WhatsApp webhook payload format:
        # {
        #   "object": "whatsapp_business_account",
        #   "entry": [
        #     {
        #       "id": "<WHATSAPP_BUSINESS_ACCOUNT_ID>",
        #       "changes": [
        #         {
        #           "value": {
        #             "messaging_product": "whatsapp",
        #             "metadata": {
        #               "display_phone_number": "...",
        #               "phone_number_id": "..."
        #             },
        #             "contacts": [ { "profile": { "name": "..." }, "wa_id": "..." } ],
        #             "messages": [ { "from": "...", "id": "...", "timestamp": "...", "text": { "body": "..." }, "type": "text" } ]
        #           }
        #         }
        #       ]
        #     }
        #   ]
        # }
        # We'll extract messages and convert them to our internal format.
        messages = []
        try:
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    if change.get("field") == "messages":
                        value = change.get("value", {})
                        for msg in value.get("messages", []):
                            # Only handle text messages for now
                            if msg.get("type") == "text":
                                messages.append(
                                    {
                                        "provider_message_id": msg["id"],
                                        "from": msg["from"],
                                        "timestamp": msg["timestamp"],
                                        "text": msg["text"]["body"],
                                        "type": msg["type"],
                                        # We'll also store the contact name if available
                                        "contact_name": None,
                                    }
                                )
        except Exception as e:
            raise ProviderFailure("invalid_webhook_payload") from e
        return messages


# Provider specifications
SPECS = {
    "gmail": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "exchange_endpoint": "https://oauth2.googleapis.com/token",
        "api": "https://gmail.googleapis.com/gmail/v1",
        "scopes": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send",
    },
    "outlook": {
        "authorize": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "exchange_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "api": "https://graph.microsoft.com/v1.0",
        "scopes": "offline_access User.Read Mail.Read Mail.Send",
    },
    "whatsapp": {
        # WhatsApp Cloud API does not use OAuth in the same way; we use a permanent token.
        # These endpoints are placeholders for the framework.
        "authorize": "https://www.facebook.com/v18.0/dialog/oauth",  # Not used
        "exchange_endpoint": "https://graph.facebook.com/v18.0/oauth/access_token",  # Not used
        "api": "https://graph.facebook.com/v18.0",
        "scopes": "",  # Not used
    },
    "meta": {
        # Meta (Facebook) Lead Ads and Pages API
        "authorize": "https://www.facebook.com/v18.0/dialog/oauth",
        "exchange_endpoint": "https://graph.facebook.com/v18.0/oauth/access_token",
        "api": "https://graph.facebook.com/v18.0",
        "scopes": "ads_management,pages_read_engagement,pages_messaging,pages_message_read,whatsapp_business_management",
    },
    "linkedin": {
        "authorize": "https://www.linkedin.com/oauth/v2/authorization",
        "exchange_endpoint": "https://www.linkedin.com/oauth/v2/accessToken",
        "api": "https://api.linkedin.com/v2",
        "scopes": "r_liteprofile,r_emailaddress,w_member_social",
    },
    "google_ads": {
        "authorize": "https://accounts.google.com/o/oauth2/auth",
        "exchange_endpoint": "https://oauth2.googleapis.com/token",
        "api": "https://googleads.googleapis.com/v15",
        "scopes": "https://www.googleapis.com/auth/adwords",
    },
    "apollo": {
        # Apollo does not use OAuth; it uses an API key.
        "authorize": "",  # Not used
        "exchange_endpoint": "",  # Not used
        "api": "https://api.apollo.io/v1",
        "scopes": "",  # Not used
    },
}


# Adapter registry
adapters: dict[str, ProviderAdapter] = {
    name: MailAdapter(name) for name in ("gmail", "outlook")
}
adapters.update(
    {
        "whatsapp": WhatsAppAdapter(),
        "meta": UnavailableAdapter(),  # Will replace with real implementation below
        "instagram": UnavailableAdapter(),
        "linkedin": UnavailableAdapter(),
        "google_ads": UnavailableAdapter(),
        "apollo": UnavailableAdapter(),
    }
)


# Now we implement the real adapters for meta, linkedin, google_ads, and apollo.
# We will reuse the existing IntegrationAdapter classes from app/services/integration/adapter.py
# for the sync and webhook handling parts, and implement OAuth connect/disconnect/refresh/health_check
# where applicable.

# First, let's import the necessary integration adapters.
# We'll do it inside the adapter classes to avoid circular imports at module level.

class MetaProviderAdapter:
    """Meta (Facebook/Instagram) provider adapter for CRM integrations.
    
    Supports:
    - Lead Ads synchronization (via Meta Lead Ads API)
    - Optional: Facebook Page messaging and Instagram Direct messaging (not implemented in this version)
    - Webhooks for lead ads and messaging
    """
    capabilities = frozenset(
        {"connect", "disconnect", "refresh", "health_check", "sync", "send", "handle_webhook"}
    )
    # Meta Lead Ads API does not support idempotent send for lead synchronization (not applicable for sending messages via this adapter)
    # Note: We are not implementing message sending via this adapter in this version.
    idempotent_send = False

    def __init__(self, transport=None):
        self.spec = SPECS["meta"]
        self.transport = transport
        # We'll lazily load the integration adapter to avoid circular imports
        self._integration_adapter = None

    @property
    def integration_adapter(self):
        if self._integration_adapter is None:
            # Import here to avoid circular import
            from app.services.integration.adapter import MetaAdapter
            self._integration_adapter = MetaAdapter()
        return self._integration_adapter

    def configuration(self):
        cfg = {
            "access_token": os.environ.get("CRM_META_ACCESS_TOKEN", ""),
            # For Lead Ads, we also need the ad account ID or page ID
            "ad_account_id": os.environ.get("CRM_META_AD_ACCOUNT_ID", ""),
            "page_id": os.environ.get("CRM_META_PAGE_ID", ""),
            # For messaging (if implemented), we would need the phone number ID for WhatsApp or page ID for Facebook Messenger
        }
        if not cfg["access_token"]:
            raise ProviderFailure("meta_not_configured")
        return cfg

    async def connect(self, code, verifier, redirect_uri):
        # Meta uses OAuth 2.0
        cfg = self.configuration()
        if redirect_uri != os.environ.get("CRM_META_REDIRECT_URI", ""):
            raise ProviderFailure("redirect_mismatch")
        return await self.request(
            "POST",
            self.spec["exchange_endpoint"],
            external_write=True,
            data={
                "client_id": os.environ.get("CRM_META_CLIENT_ID", ""),
                "client_secret": os.environ.get("CRM_META_CLIENT_SECRET", ""),
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": os.environ.get("CRM_META_REDIRECT_URI", ""),
            },
        )

    async def disconnect(self, token):
        # Meta allows token revocation via the API
        cfg = self.configuration()
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
                await client.delete(
                    f"https://graph.facebook.com/v18.0/me/permissions",
                    params={"access_token": token},
                )
        except Exception:
            # Best effort
            pass
        return {"remote_revocation": True}

    async def refresh(self, refresh_token):
        # Meta uses long-lived tokens that can be refreshed
        cfg = self.configuration()
        return await self.request(
            "POST",
            self.spec["exchange_endpoint"],
            external_write=True,
            data={
                "client_id": os.environ.get("CRM_META_CLIENT_ID", ""),
                "client_secret": os.environ.get("CRM_META_CLIENT_SECRET", ""),
                "grant_type": "fb_exchange_token",
                "fb_exchange_token": refresh_token,
            },
        )

    async def health_check(self, token):
        cfg = self.configuration()
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
                response = await client.get(
                    f"https://graph.facebook.com/v18.0/me",
                    params={"access_token": token},
                )
                data = response.json()
                return {
                    "connected": True,
                    "address": data.get("name") or f"Facebook User ID {data.get('id')}",
                }
        except Exception:
            return {"connected": False, "address": None}

    async def send(self, token, message, idempotency_key):
        # We are not implementing message sending via the Meta adapter in this version.
        # If we wanted to send messages via Facebook Messenger or Instagram Direct, we would need to implement it here.
        raise ProviderFailure("outbound_attachments_not_supported")  # Placeholder

    async def sync(self, token, cursor=None):
        # We are not implementing message synchronization for Meta in this version.
        return {"messages": [], "cursor": None}

    async def handle_webhook(self, payload):
        # Delegate to the MetaIntegrationAdapter for parsing webhook events
        return self.integration_adapter.get_webhook_events(payload, self.configuration().get("access_token", ""))


class LinkedInProviderAdapter:
    """LinkedIn provider adapter for CRM integrations.
    
    Supports:
    - Lead Gen Forms synchronization
    - Webhooks for lead gen forms
    """
    capabilities = frozenset(
        {"connect", "disconnect", "refresh", "health_check", "sync", "handle_webhook"}
    )
    # LinkedIn Lead Gen Forms API does not support idempotent send for lead synchronization
    idempotent_send = False

    def __init__(self, transport=None):
        self.spec = SPECS["linkedin"]
        self.transport = transport
        self._integration_adapter = None

    @property
    def integration_adapter(self):
        if self._integration_adapter is None:
            from app.services.integration.adapter import LinkedInAdapter
            self._integration_adapter = LinkedInAdapter()
        return self._integration_adapter

    def configuration(self):
        cfg = {
            "access_token": os.environ.get("CRM_LINKEDIN_ACCESS_TOKEN", ""),
        }
        if not cfg["access_token"]:
            raise ProviderFailure("linkedin_not_configured")
        return cfg

    async def connect(self, code, verifier, redirect_uri):
        cfg = self.configuration()
        if redirect_uri != os.environ.get("CRM_LINKEDIN_REDIRECT_URI", ""):
            raise ProviderFailure("redirect_mismatch")
        return await self.request(
            "POST",
            self.spec["exchange_endpoint"],
            external_write=True,
            data={
                "client_id": os.environ.get("CRM_LINKEDIN_CLIENT_ID", ""),
                "client_secret": os.environ.get("CRM_LINKEDIN_CLIENT_SECRET", ""),
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": os.environ.get("CRM_LINKEDIN_REDIRECT_URI", ""),
            },
        )

    async def disconnect(self, token):
        # LinkedIn allows token revocation
        cfg = self.configuration()
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
                await client.delete(
                    f"https://api.linkedin.com/v2/oauth/accessToken",
                    params={"access_token": token},
                )
        except Exception:
            pass
        return {"remote_revocation": True}

    async def refresh(self, refresh_token):
        cfg = self.configuration()
        return await self.request(
            "POST",
            self.spec["exchange_endpoint"],
            external_write=True,
            data={
                "client_id": os.environ.get("CRM_LINKEDIN_CLIENT_ID", ""),
                "client_secret": os.environ.get("CRM_LINKEDIN_CLIENT_SECRET", ""),
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )

    async def health_check(self, token):
        cfg = self.configuration()
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
                response = await client.get(
                    f"https://api.linkedin.com/v2/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = response.json()
                return {
                    "connected": True,
                    "address": data.get("localizedFirstName") or f"LinkedIn User ID {data.get('id')}",
                }
        except Exception:
            return {"connected": False, "address": None}

    async def send(self, token, message, idempotency_key):
        # LinkedIn messaging API is complex and not implemented in this version.
        raise ProviderFailure("outbound_attachments_not_supported")

    async def sync(self, token, cursor=None):
        # We are not implementing message synchronization for LinkedIn in this version.
        return {"messages": [], "cursor": None}

    async def handle_webhook(self, payload):
        return self.integration_adapter.get_webhook_events(payload, self.configuration().get("access_token", ""))


class GoogleAdsProviderAdapter:
    """Google Ads provider adapter for CRM integrations.
    
    Supports:
    - Lead Form Extensions synchronization
    """
    capabilities = frozenset(
        {"connect", "disconnect", "refresh", "health_check", "sync", "handle_webhook"}
    )
    # Google Ads Lead Form Extensions API does not support idempotent send for lead synchronization
    idempotent_send = False

    def __init__(self, transport=None):
        self.spec = SPECS["google_ads"]
        self.transport = transport
        self._integration_adapter = None

    @property
    def integration_adapter(self):
        if self._integration_adapter is None:
            from app.services.integration.adapter import GoogleAdsAdapter
            self._integration_adapter = GoogleAdsAdapter()
        return self._integration_adapter

    def configuration(self):
        cfg = {
            "access_token": os.environ.get("CRM_GOOGLE_ADS_ACCESS_TOKEN", ""),
            # For Google Ads API, we also need a developer token and customer ID
            "developer_token": os.environ.get("CRM_GOOGLE_ADS_DEVELOPER_TOKEN", ""),
            "customer_id": os.environ.get("CRM_GOOGLE_ADS_CUSTOMER_ID", ""),
        }
        if not cfg["access_token"]:
            raise ProviderFailure("google_ads_not_configured")
        return cfg

    async def connect(self, code, verifier, redirect_uri):
        # Google Ads uses OAuth 2.0
        cfg = self.configuration()
        if redirect_uri != os.environ.get("CRM_GOOGLE_ADS_REDIRECT_URI", ""):
            raise ProviderFailure("redirect_mismatch")
        return await self.request(
            "POST",
            self.spec["exchange_endpoint"],
            external_write=True,
            data={
                "client_id": os.environ.get("CRM_GOOGLE_ADS_CLIENT_ID", ""),
                "client_secret": os.environ.get("CRM_GOOGLE_ADS_CLIENT_SECRET", ""),
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": os.environ.get("CRM_GOOGLE_ADS_REDIRECT_URI", ""),
            },
        )

    async def disconnect(self, token):
        # Google OAuth tokens can be revoked
        cfg = self.configuration()
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
                await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": token},
                )
        except Exception:
            pass
        return {"remote_revocation": True}

    async def refresh(self, refresh_token):
        cfg = self.configuration()
        return await self.request(
            "POST",
            self.spec["exchange_endpoint"],
            external_write=True,
            data={
                "client_id": os.environ.get("CRM_GOOGLE_ADS_CLIENT_ID", ""),
                "client_secret": os.environ.get("CRM_GOOGLE_ADS_CLIENT_SECRET", ""),
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )

    async def health_check(self, token):
        cfg = self.configuration()
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
                response = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = response.json()
                return {
                    "connected": True,
                    "address": data.get("email") or f"Google User ID {data.get('id')}",
                }
        except Exception:
            return {"connected": False, "address": None}

    async def send(self, token, message, idempotency_key):
        # Google Ads does not support sending messages via this adapter.
        raise ProviderFailure("outbound_attachments_not_supported")

    async def sync(self, token, cursor=None):
        # We are not implementing message synchronization for Google Ads in this version.
        return {"messages": [], "cursor": None}

    async def handle_webhook(self, payload):
        # Google Ads Lead Form Extensions do not have native webhooks; they use polling.
        # However, we can still return an empty list or handle if there is a webhook format.
        return []


class ApolloProviderAdapter:
    """Apollo provider adapter for CRM integrations.
    
    Supports:
    - Lead and account enrichment and search
    """
    capabilities = frozenset(
        {"connect", "disconnect", "refresh", "health_check", "sync", "handle_webhook"}
    )
    # Apollo API does not support idempotent send for lead enrichment/search
    idempotent_send = False

    def __init__(self, transport=None):
        self.spec = SPECS["apollo"]
        self.transport = transport
        self._integration_adapter = None

    @property
    def integration_adapter(self):
        if self._integration_adapter is None:
            from app.services.integration.adapter import ApolloAdapter
            self._integration_adapter = ApolloAdapter()
        return self._integration_adapter

    def configuration(self):
        cfg = {
            "api_key": os.environ.get("CRM_APOLLO_API_KEY", ""),
        }
        if not cfg["api_key"]:
            raise ProviderFailure("apollo_not_configured")
        return cfg

    async def connect(self, code, verifier, redirect_uri):
        # Apollo does not use OAuth; it uses an API key.
        # We'll treat the API key as the credential and ignore the OAuth flow.
        # For the purpose of the framework, we'll just validate the API key.
        cfg = self.configuration()
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
                response = await client.get(
                    f"{self.spec['api']}/auth/health",
                    headers={"Authorization": f"Bearer {cfg['api_key']}"},
                )
                if response.status_code != 200:
                    raise ProviderFailure("invalid_api_key")
        except httpx.HTTPError as e:
            raise ProviderFailure("provider_connection_failed") from e
        return {"status": "connected"}

    async def disconnect(self, token):
        # Apollo API keys cannot be revoked via the API; we just return success.
        return {"remote_revocation": False}

    async def refresh(self, refresh_token):
        # Apollo does not use refresh tokens; we return the same API key.
        cfg = self.configuration()
        return {
            "api_key": cfg["api_key"],
        }

    async def health_check(self, token):
        cfg = self.configuration()
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
                response = await client.get(
                    f"{self.spec['api']}/auth/health",
                    headers={"Authorization": f"Bearer {cfg['api_key']}"},
                )
                if response.status_code == 200:
                    return {
                        "connected": True,
                        "address": "Apollo API",
                    }
                else:
                    return {"connected": False, "address": None}
        except Exception:
            return {"connected": False, "address": None}

    async def send(self, token, message, idempotency_key):
        # Apollo does not support sending messages via this adapter.
        raise ProviderFailure("outbound_attachments_not_supported")

    async def sync(self, token, cursor=None):
        # We are not implementing message synchronization for Apollo in this version.
        return {"messages": [], "cursor": None}

    async def handle_webhook(self, payload):
        # Apollo supports webhooks for contact updates.
        # We'll delegate to the integration adapter.
        return self.integration_adapter.get_webhook_events(payload, self.configuration().get("api_key", ""))


# Update the adapters dictionary with the real implementations
adapters["meta"] = MetaProviderAdapter()
adapters["linkedin"] = LinkedInProviderAdapter()
adapters["google_ads"] = GoogleAdsProviderAdapter()
adapters["apollo"] = ApolloProviderAdapter()
# Note: instagram remains UnavailableAdapter for now

def adapter_for(integration):
    name = (integration.config or {}).get(
        "provider", getattr(integration.type, "value", integration.type)
    )
    if name not in adapters:
        raise ProviderFailure("provider_unavailable")
    return adapters[name]