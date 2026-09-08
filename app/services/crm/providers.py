"""Capability-based providers. Unsupported operations fail explicitly."""

import base64
import os
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.parse import urlencode
from typing import Protocol
import httpx


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
}


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
            items = [
                {
                    "provider_message_id": r["id"],
                    "thread_id": r.get("conversationId", r["id"]),
                    "subject": r.get("subject") or "(no subject)",
                    "body": r.get("bodyPreview") or "(empty message)",
                    "sender": r.get("from", {})
                    .get("emailAddress", {})
                    .get("address", ""),
                    "recipient": next(iter(r.get("toRecipients", [])), {})
                    .get("emailAddress", {})
                    .get("address", ""),
                    "occurred_at": r["receivedDateTime"],
                    "attachments": [],
                }
                for r in data.get("value", [])
            ]
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
                            "provider_attachment_id": body["attachmentId"],
                        }
                    )
                stack.extend((child, depth + 1) for child in part.get("parts", []))
            items.append(
                {
                    "provider_message_id": item["id"],
                    "thread_id": item["threadId"],
                    "subject": fields.get("subject") or "(no subject)",
                    "body": "\n".join(parts)
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


adapters: dict[str, ProviderAdapter] = {name: MailAdapter(name) for name in SPECS}
adapters.update(
    {
        name: UnavailableAdapter()
        for name in (
            "whatsapp",
            "meta",
            "instagram",
            "linkedin",
            "google_ads",
            "apollo",
        )
    }
)


def adapter_for(integration):
    name = (integration.config or {}).get(
        "provider", getattr(integration.type, "value", integration.type)
    )
    if name not in adapters:
        raise ProviderFailure("provider_unavailable")
    return adapters[name]
