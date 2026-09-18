"""Capability-based providers. Unsupported operations fail explicitly."""

import base64
import os
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.parse import urlencode, urlsplit, quote
from typing import Protocol
import httpx
import json
import re


class ProviderFailure(RuntimeError):
    def __init__(self, code="provider_failure", *, retryable=False, uncertain=False, retry_after=60):
        super().__init__(code)
        self.code, self.retryable, self.uncertain = code, retryable, uncertain
        self.retry_after = min(3600, max(1, int(retry_after)))


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


class MailAdapter(UnavailableAdapter):
    capabilities = frozenset(
        {"connect", "oauth", "disconnect", "refresh", "health_check", "sync", "send"}
    )
    # Neither API promises deduplication of retries by a caller-supplied key.
    idempotent_send = False

    def __init__(self, name, transport=None):
        self.name, self.spec, self.transport = name, SPECS[name], transport
        self.config = {}

    def configuration(self):
        prefix = "CRM_" + self.name.upper()
        values = {
            key: os.environ.get(prefix + "_" + key.upper(), "")
            for key in ("client_id", "client_secret", "redirect_uri")
        }
        try:
            uri = urlsplit(values["redirect_uri"])
            valid_redirect = (uri.scheme == "https" and bool(uri.hostname) and not uri.username
                              and not uri.password and not uri.fragment and uri.port in {None, 443}
                              and "\\" not in values["redirect_uri"])
        except ValueError:
            valid_redirect = False
        if not all(values.values()) or not valid_redirect:
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
        if self.name in {"gmail", "google_ads"}:
            params.update(access_type="offline", prompt="consent")
        return self.spec["authorize"] + "?" + urlencode(params)

    async def request(self, method, url, *, external_write=False, **kwargs):
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=30, follow_redirects=False
            ) as client:
                response = await client.request(method, url, **kwargs)
                if len(response.content) > 5_000_000:
                    raise ProviderFailure("provider_response_too_large", uncertain=external_write)
        except httpx.HTTPError:
            raise ProviderFailure(
                "transport_error",
                retryable=not external_write,
                uncertain=external_write,
            ) from None
        if response.status_code >= 300:
            raise ProviderFailure(
                f"provider_http_{response.status_code}",
                retryable=response.status_code == 429
                or (response.status_code >= 500 and not external_write),
                uncertain=external_write and response.status_code >= 500,
                retry_after=response.headers.get("retry-after", "60") if response.headers.get("retry-after", "60").isdigit() else 60,
            )
        try:
            result = response.json() if response.content else {}
            if not isinstance(result, dict) or result.get("error"):
                raise ProviderFailure("invalid_provider_response", uncertain=external_write)
            return result
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
        if self.name in {"gmail", "google_ads"}:
            await self.request(
                "POST",
                "https://oauth2.googleapis.com/revoke",
                external_write=True,
                data={"token": token},
            )
        return {"remote_revocation": self.name in {"gmail", "google_ads"}}

    async def health_check(self, token):
        path = "/users/me/profile" if self.name == "gmail" else "/me"
        data = await self.request(
            "GET", self.spec["api"] + path, headers={"Authorization": "Bearer " + token}
        )
        if not (data.get("emailAddress") if self.name == "gmail" else data.get("id")):
            raise ProviderFailure("invalid_identity_response")
        return {
            "connected": True,
            "address": data.get("emailAddress")
            or data.get("mail")
            or data.get("userPrincipalName"),
        }

    async def send(self, token, message, idempotency_key):
        if message.get("attachments"):
            raise ProviderFailure("outbound_attachments_not_supported")
        headers = {"Authorization": "Bearer " + token, "Prefer": 'IdType="ImmutableId"'}
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
            if not result.get("id"):
                raise ProviderFailure("invalid_send_response", uncertain=True)
            return {
                "provider_message_id": result["id"],
                "thread_id": result.get("threadId"),
                "status": "sent",
            }
        draft = await self.request(
            "POST",
            self.spec["api"] + "/me/messages",
            external_write=True,
            headers=headers,
            json={
                    "subject": message["subject"],
                    "body": {"contentType": "Text", "content": message["body"]},
                    "toRecipients": [
                        {"emailAddress": {"address": message["recipient"]}}
                    ],
            },
        )
        if not draft.get("id"):
            raise ProviderFailure("invalid_draft_response", uncertain=True)
        await self.request("POST", self.spec["api"] + "/me/messages/" + quote(draft["id"], safe="") + "/send",
                           external_write=True, headers=headers)
        return {"provider_message_id": draft["id"], "thread_id": draft.get("conversationId"), "status": "sent"}

    async def sync(self, token, cursor=None):
        if self.name == "outlook":
            return await outlook_sync(self, token, cursor)
        headers = {"Authorization": "Bearer " + token}
        state = decode_cursor(cursor)
        if state.get("mode") == "history":
            return await gmail_history(self, token, state)
        if not state:
            profile = await self.request("GET", self.spec["api"] + "/users/me/profile", headers=headers)
            state = {"history_id": profile["historyId"]}
        params = {"maxResults": 25, "labelIds": "INBOX"}
        if state.get("page"):
            params["pageToken"] = state["page"]
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
        next_page = data.get("nextPageToken")
        next_state = {**state, "page": next_page} if next_page else {"mode": "history", "history_id": state["history_id"]}
        return {"messages": items, "cursor": encode_cursor(next_state), "has_more": bool(next_page)}

    async def handle_webhook(self, payload):
        raise ProviderFailure("provider_push_contract_not_configured")



def encode_cursor(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def decode_cursor(value):
    if not value:
        return {}
    try:
        result = json.loads(value)
        if not isinstance(result, dict) or len(value) > 16000:
            raise ValueError
        return result
    except (TypeError, ValueError):
        raise ProviderFailure("invalid_cursor") from None


async def outlook_sync(adapter, token, cursor):
    path = "/me/mailFolders/inbox/messages/delta"
    url = adapter.spec["api"] + path
    params = {"$select": "id,conversationId,subject,bodyPreview,from,toRecipients,receivedDateTime", "$top": 25}
    if cursor:
        parsed = urlsplit(cursor)
        # Provider-produced opaque links are persisted on the server. Still constrain the
        # authority and resource on every use so compromised cursors cannot cause SSRF.
        if (parsed.scheme != "https" or parsed.netloc != "graph.microsoft.com"
                or parsed.path != "/v1.0" + path or parsed.fragment or len(cursor) > 16000):
            raise ProviderFailure("invalid_cursor")
        url, params = cursor, None
    data = await adapter.request("GET", url, params=params,
                                 headers={"Authorization": "Bearer " + token, "Prefer": 'IdType="ImmutableId"'})
    messages = []
    for item in data.get("value", []):
        if "@removed" in item:
            continue  # CRM audit history is retained when mail is deleted upstream.
        messages.append({"provider_message_id": item["id"], "thread_id": item.get("conversationId", item["id"]),
                         "subject": item.get("subject") or "(no subject)", "body": item.get("bodyPreview") or "(empty message)",
                         "sender": item.get("from", {}).get("emailAddress", {}).get("address", ""),
                         "recipient": next(iter(item.get("toRecipients", [])), {}).get("emailAddress", {}).get("address", ""),
                         "occurred_at": item["receivedDateTime"], "attachments": []})
    next_url = data.get("@odata.nextLink") or data.get("@odata.deltaLink")
    if not next_url:
        raise ProviderFailure("missing_delta_cursor")
    return {"messages": messages, "cursor": next_url, "has_more": bool(data.get("@odata.nextLink"))}


async def gmail_history(adapter, token, state):
    headers = {"Authorization": "Bearer " + token}
    params = {"startHistoryId": state["history_id"], "historyTypes": "messageAdded", "maxResults": 25}
    if state.get("page"):
        params["pageToken"] = state["page"]
    data = await adapter.request("GET", adapter.spec["api"] + "/users/me/history", headers=headers, params=params)
    messages = []
    seen = set()
    for history in data.get("history", []):
        for entry in history.get("messagesAdded", []):
            ref = entry["message"]
            if ref["id"] in seen or "INBOX" not in ref.get("labelIds", ["INBOX"]):
                continue
            seen.add(ref["id"])
            item = await adapter.request("GET", adapter.spec["api"] + "/users/me/messages/" + quote(ref["id"], safe=""),
                                         headers=headers, params={"format": "full"})
            fields = {h["name"].lower(): h["value"] for h in item.get("payload", {}).get("headers", [])}
            parts = []
            stack = [(item.get("payload", {}), 0)]
            while stack:
                part, depth = stack.pop()
                if depth > 8:
                    raise ProviderFailure("message_mime_too_deep")
                value = part.get("body", {}).get("data")
                if part.get("mimeType") == "text/plain" and value:
                    parts.append(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf-8", errors="replace"))
                stack.extend((child, depth + 1) for child in part.get("parts", []))
            messages.append({"provider_message_id": item["id"], "thread_id": item.get("threadId", item["id"]),
                             "subject": fields.get("subject") or "(no subject)", "body": "\n".join(parts) or item.get("snippet") or "(empty message)",
                             "sender": parseaddr(fields.get("from", ""))[1], "recipient": parseaddr(fields.get("to", ""))[1],
                             "occurred_at": datetime.fromtimestamp(int(item["internalDate"]) / 1000, timezone.utc).isoformat(), "attachments": []})
    page = data.get("nextPageToken")
    next_state = {**state, "page": page} if page else {"mode": "history", "history_id": data["historyId"]}
    return {"messages": messages, "cursor": encode_cursor(next_state), "has_more": bool(page)}


class OAuthProvider(MailAdapter):
    capabilities = frozenset({"connect", "oauth", "disconnect", "health_check"})
    send = sync = handle_webhook = refresh = UnavailableAdapter.unsupported

    async def disconnect(self, token):
        # A local disconnect is explicit. Never pretend to revoke a provider token.
        return {"remote_revocation": False}

    async def health_check(self, token):
        data = await self.request("GET", self.spec["api"] + "/userinfo", headers={"Authorization": "Bearer " + token})
        if not data.get("sub"):
            raise ProviderFailure("invalid_identity_response")
        return {"connected": True, "provider_account_id": str(data["sub"]), "address": data.get("email")}


class MetaProviderAdapter(OAuthProvider):
    capabilities = frozenset({"connect", "oauth", "disconnect", "health_check", "sync", "handle_webhook"})

    def __init__(self, transport=None, name="meta", config=None):
        super().__init__(name, transport)
        self.config = config or {}

    def graph_api(self):
        version = os.environ.get("CRM_META_GRAPH_VERSION", "")
        if not re.fullmatch(r"v[0-9]{1,2}\.0", version):
            raise ProviderFailure("graph_api_version_not_configured")
        return "https://graph.facebook.com/" + version

    def authorization_url(self, state, challenge):
        cfg = self.configuration()
        return "https://www.facebook.com/" + self.graph_api().rsplit("/", 1)[-1] + "/dialog/oauth?" + urlencode({
            "client_id": cfg["client_id"], "redirect_uri": cfg["redirect_uri"], "response_type": "code",
            "scope": self.spec["scopes"], "state": state})

    async def connect(self, code, verifier, redirect_uri):
        cfg = self.configuration()
        if redirect_uri != cfg["redirect_uri"]:
            raise ProviderFailure("redirect_mismatch")
        return await self.request("POST", self.graph_api() + "/oauth/access_token", external_write=True,
                                  data={**cfg, "code": code})

    async def health_check(self, token):
        data = await self.request("GET", self.graph_api() + "/me", params={"fields": "id,name"},
                                  headers={"Authorization": "Bearer " + token})
        if not data.get("id"):
            raise ProviderFailure("invalid_identity_response")
        return {"connected": True, "provider_account_id": data["id"], "address": data.get("name")}

    async def sync(self, token, cursor=None):
        form = self.config.get("form_id")
        if not form or not str(form).isdigit():
            raise ProviderFailure("lead_form_not_configured")
        state = decode_cursor(cursor)
        params = {"limit": 25, "fields": "id,created_time,field_data"}
        if state.get("after"):
            params["after"] = state["after"]
        if state.get("since"):
            params["since"] = state["since"]
        started = state.get("started") or int(datetime.now(timezone.utc).timestamp())
        data = await self.request("GET", self.graph_api() + "/" + str(form) + "/leads", params=params,
                                  headers={"Authorization": "Bearer " + token})
        after = data.get("paging", {}).get("cursors", {}).get("after") if data.get("paging", {}).get("next") else None
        next_state = {**state, "started": started, "after": after} if after else {"since": started}
        return {"leads": [normalize_meta_lead(row) for row in data.get("data", [])],
                "cursor": encode_cursor(next_state), "has_more": bool(after)}

    async def handle_webhook(self, payload):
        events = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") == "leadgen":
                    value = change["value"]
                    events.append({"kind": "lead_reference", "provider_event_id": str(value["leadgen_id"]),
                                   "lead_id": str(value["leadgen_id"]), "account_id": str(value["page_id"]),
                                   "timestamp": int(value["created_time"])})
            for value in entry.get("messaging", []):
                if value.get("message", {}).get("is_echo"):
                    continue
                message = value.get("message", {})
                if message.get("mid"):
                    if not isinstance(message.get("text"), str):
                        raise ProviderFailure("unsupported_social_message_type")
                    events.append({"kind": "message", "provider_event_id": message["mid"], "account_id": str(entry["id"]),
                                   "timestamp": int(value["timestamp"]) // 1000,
                                   "message": {"provider_message_id": message["mid"], "thread_id": str(value["sender"]["id"]),
                                               "provider_contact_id": str(value["sender"]["id"]), "channel": "social",
                                               "subject": "Social conversation", "body": message["text"], "sender": str(value["sender"]["id"]),
                                               "recipient": str(value["recipient"]["id"]),
                                               "occurred_at": datetime.fromtimestamp(int(value["timestamp"]) / 1000, timezone.utc).isoformat(), "attachments": []}})
        if not events:
            raise ProviderFailure("unsupported_webhook_event")
        return events

    async def fetch_lead(self, token, lead_id):
        data = await self.request("GET", self.graph_api() + "/" + quote(lead_id, safe=""),
                                  params={"fields": "id,created_time,field_data"}, headers={"Authorization": "Bearer " + token})
        return normalize_meta_lead(data)


class InstagramProviderAdapter(MetaProviderAdapter):
    # Instagram messaging arrives through Meta's signed page webhook. Historical
    # inbox export and arbitrary outreach are deliberately not advertised.
    capabilities = frozenset({"connect", "oauth", "disconnect", "health_check", "handle_webhook"})
    sync = UnavailableAdapter.unsupported

    def __init__(self, transport=None, config=None):
        super().__init__(transport, "instagram", config)


class WhatsAppAdapter(MetaProviderAdapter):
    capabilities = frozenset({"configure", "disconnect", "health_check", "send", "handle_webhook"})
    connect = refresh = sync = UnavailableAdapter.unsupported

    def __init__(self, transport=None, config=None):
        super().__init__(transport, "whatsapp", config)

    def configuration(self):
        self.graph_api()
        return {}

    def phone_id(self):
        value = str(self.config.get("phone_number_id", ""))
        if not value.isdigit():
            raise ProviderFailure("phone_number_id_not_configured")
        return value

    async def health_check(self, token):
        data = await self.request("GET", self.graph_api() + "/" + self.phone_id(),
                                  params={"fields": "id,display_phone_number,verified_name"}, headers={"Authorization": "Bearer " + token})
        if str(data.get("id")) != self.phone_id():
            raise ProviderFailure("phone_number_identity_mismatch")
        return {"connected": True, "provider_account_id": data["id"], "address": data.get("display_phone_number")}

    async def send(self, token, message, idempotency_key):
        if message.get("attachments"):
            raise ProviderFailure("outbound_attachments_not_supported")
        if not re.fullmatch(r"\+?[1-9][0-9]{6,14}", message["recipient"]):
            raise ProviderFailure("invalid_phone_number")
        if len(message["body"]) > 4096:
            raise ProviderFailure("whatsapp_message_too_long")
        data = await self.request("POST", self.graph_api() + "/" + self.phone_id() + "/messages", external_write=True,
                                  headers={"Authorization": "Bearer " + token},
                                  json={"messaging_product": "whatsapp", "recipient_type": "individual", "type": "text",
                                        "to": message["recipient"].lstrip("+"), "text": {"body": message["body"]}})
        try:
            message_id = data["messages"][0]["id"]
        except (KeyError, IndexError, TypeError):
            raise ProviderFailure("invalid_send_response", uncertain=True) from None
        return {"provider_message_id": message_id, "status": "sent"}

    async def handle_webhook(self, payload):
        if payload.get("object") != "whatsapp_business_account":
            raise ProviderFailure("invalid_webhook_object")
        events = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                account = str(value.get("metadata", {}).get("phone_number_id", ""))
                for message in value.get("messages", []):
                    if message.get("type") != "text":
                        raise ProviderFailure("unsupported_whatsapp_message_type")
                    sender = "+" + message["from"].lstrip("+")
                    stamp = int(message["timestamp"])
                    events.append({"kind": "message", "provider_event_id": message["id"], "account_id": account, "timestamp": stamp,
                                   "message": {"provider_message_id": message["id"], "thread_id": sender,
                                               "provider_contact_id": message["from"], "phone_verified": True, "channel": "whatsapp",
                                               "subject": "WhatsApp conversation", "body": message["text"]["body"], "sender": sender,
                                               "recipient": "+" + str(value.get("metadata", {}).get("display_phone_number", "")).lstrip("+"),
                                               "occurred_at": datetime.fromtimestamp(stamp, timezone.utc).isoformat(), "attachments": []}})
                for item in value.get("statuses", []):
                    if item.get("status") not in {"sent", "delivered", "read", "failed"}:
                        raise ProviderFailure("unsupported_delivery_status")
                    events.append({"kind": "status", "provider_event_id": item["id"] + ":" + item["status"],
                                   "provider_message_id": item["id"], "status": item["status"], "account_id": account,
                                   "timestamp": int(item["timestamp"]), "error_code": str(next(iter(item.get("errors", [])), {}).get("code", ""))})
        if not events:
            raise ProviderFailure("unsupported_webhook_event")
        return events


class LinkedInProviderAdapter(OAuthProvider):
    def __init__(self, transport=None):
        super().__init__("linkedin", transport)


class GoogleAdsProviderAdapter(OAuthProvider):
    capabilities = frozenset({"connect", "oauth", "disconnect", "refresh", "health_check", "sync", "handle_webhook"})
    refresh = MailAdapter.refresh
    disconnect = MailAdapter.disconnect

    def __init__(self, transport=None, config=None):
        super().__init__("google_ads", transport)
        self.config = config or {}

    def ads_config(self):
        version = os.environ.get("CRM_GOOGLE_ADS_API_VERSION", "")
        developer_token = os.environ.get("CRM_GOOGLE_ADS_DEVELOPER_TOKEN", "")
        customer = str(self.config.get("customer_id", "")).replace("-", "")
        if not re.fullmatch(r"v[0-9]{1,2}", version) or not developer_token or not customer.isdigit():
            raise ProviderFailure("google_ads_not_configured")
        return version, developer_token, customer

    async def query(self, token, query, page=None):
        version, developer, customer = self.ads_config()
        body = {"query": query}
        if page:
            body["pageToken"] = page
        return await self.request("POST", f"https://googleads.googleapis.com/{version}/customers/{customer}/googleAds:search",
                                  headers={"Authorization": "Bearer " + token, "developer-token": developer}, json=body)

    async def health_check(self, token):
        data = await self.query(token, "SELECT customer.id, customer.descriptive_name FROM customer LIMIT 1")
        rows = data.get("results", [])
        if not rows:
            raise ProviderFailure("customer_not_accessible")
        return {"connected": True, "provider_account_id": str(rows[0]["customer"]["id"]), "address": rows[0]["customer"].get("descriptiveName")}

    async def sync(self, token, cursor=None):
        state = decode_cursor(cursor)
        query = "SELECT lead_form_submission_data.id, lead_form_submission_data.submission_date_time, lead_form_submission_data.lead_form_submission_fields FROM lead_form_submission_data"
        if state.get("since"):
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", state["since"]):
                raise ProviderFailure("invalid_cursor")
            query += " WHERE lead_form_submission_data.submission_date_time >= '" + state["since"] + "'"
        # A date watermark deliberately overlaps the last day; provider IDs dedupe
        # it so submissions arriving during pagination cannot be skipped.
        started = state.get("started") or datetime.now(timezone.utc).date().isoformat()
        data = await self.query(token, query, state.get("page"))
        leads = []
        for row in data.get("results", []):
            value = row["leadFormSubmissionData"]
            fields = {f["fieldType"]: f.get("fieldValue", "") for f in value.get("leadFormSubmissionFields", [])}
            leads.append(normalize_lead(str(value["id"]), fields, "google_ads", value.get("submissionDateTime")))
        page = data.get("nextPageToken")
        return {"leads": leads, "cursor": encode_cursor({**state, "page": page, "started": started} if page else {"since": started}), "has_more": bool(page)}

    async def handle_webhook(self, payload):
        # Google Ads sends a shared google_key, not a cryptographic timestamp.
        # Authentication is performed by ingress; event-id dedupe is permanent.
        fields = {r["column_id"]: r.get("string_value", "") for r in payload.get("user_column_data", [])}
        return [{"kind": "lead", "provider_event_id": str(payload["lead_id"]), "account_id": str(payload.get("form_id", "")),
                 "lead": normalize_lead(str(payload["lead_id"]), fields, "google_ads", None)}]


class ApolloProviderAdapter(OAuthProvider):
    capabilities = frozenset({"configure", "disconnect", "health_check", "enrich"})
    connect = refresh = sync = handle_webhook = UnavailableAdapter.unsupported

    def __init__(self, transport=None):
        super().__init__("apollo", transport)

    def configuration(self):
        return {}

    async def health_check(self, token):
        data = await self.request("GET", self.spec["api"] + "/auth/health", headers={"X-Api-Key": token})
        if data.get("is_logged_in") is not True:
            raise ProviderFailure("invalid_api_key")
        return {"connected": True, "address": "Apollo API"}

    async def enrich(self, token, identity):
        # This operation may consume plan credits. Runtime activation is separate
        # from implementation and defaults off. Tests inject an external transport.
        if self.transport is None and os.environ.get("CRM_APOLLO_ENRICHMENT_ENABLED") != "true":
            raise ProviderFailure("credit_consuming_operation_disabled")
        if not (identity.get("id") or identity.get("email")):
            raise ProviderFailure("verified_identity_required")
        params = {k: identity[k] for k in ("id", "email") if identity.get(k)}
        params.update(reveal_personal_emails=False, reveal_phone_number=False)
        data = await self.request("POST", self.spec["api"] + "/people/match", params=params, headers={"X-Api-Key": token})
        person = data.get("person")
        if not person or not person.get("id"):
            return {"status": "not_found", "provider": "apollo", "person": None}
        return {"status": "matched", "provider": "apollo", "provider_id": person["id"],
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "person": {k: person.get(k) for k in ("first_name", "last_name", "email", "email_status", "title", "linkedin_url", "organization_id")}}


def normalize_lead(provider_id, fields, provider, occurred_at):
    fields = {str(k).lower(): v for k, v in fields.items()}
    return {"provider_id": provider_id, "provider": provider, "email": fields.get("email") or fields.get("work_email"),
            "phone": fields.get("phone_number"), "first_name": fields.get("first_name") or fields.get("full_name") or "New",
            "last_name": fields.get("last_name") or "Lead", "occurred_at": occurred_at,
            "email_verified": False, "phone_verified": False}


def normalize_meta_lead(row):
    fields = {f["name"]: next(iter(f.get("values", [])), "") for f in row.get("field_data", [])}
    return normalize_lead(str(row["id"]), fields, "meta", row.get("created_time"))


SPECS = {
    "gmail": {"authorize": "https://accounts.google.com/o/oauth2/v2/auth", "exchange_endpoint": "https://oauth2.googleapis.com/token",
              "api": "https://gmail.googleapis.com/gmail/v1", "scopes": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"},
    "outlook": {"authorize": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize", "exchange_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                "api": "https://graph.microsoft.com/v1.0", "scopes": "offline_access User.Read Mail.ReadWrite Mail.Send"},
    "linkedin": {"authorize": "https://www.linkedin.com/oauth/v2/authorization", "exchange_endpoint": "https://www.linkedin.com/oauth/v2/accessToken",
                 "api": "https://api.linkedin.com/v2", "scopes": "openid profile email"},
    "google_ads": {"authorize": "https://accounts.google.com/o/oauth2/v2/auth", "exchange_endpoint": "https://oauth2.googleapis.com/token",
                   "api": "https://googleads.googleapis.com", "scopes": "https://www.googleapis.com/auth/adwords"},
    "meta": {"scopes": "pages_show_list,pages_read_engagement,leads_retrieval"},
    "instagram": {"scopes": "instagram_basic,instagram_manage_messages,pages_manage_metadata"},
    "whatsapp": {}, "apollo": {"api": "https://api.apollo.io/api/v1"},
}

adapters = {"gmail": MailAdapter("gmail"), "outlook": MailAdapter("outlook"), "meta": MetaProviderAdapter(),
            "instagram": InstagramProviderAdapter(), "linkedin": LinkedInProviderAdapter(), "google_ads": GoogleAdsProviderAdapter(),
            "whatsapp": WhatsAppAdapter(), "apollo": ApolloProviderAdapter()}


def adapter_for(integration):
    import copy
    name = (integration.config or {}).get("provider", getattr(integration.type, "value", integration.type))
    if name not in adapters:
        raise ProviderFailure("provider_unavailable")
    adapter = adapters[name]
    # Config is per integration, never put tenant state into the shared registry.
    if type(adapter) in {MetaProviderAdapter, InstagramProviderAdapter, WhatsAppAdapter, GoogleAdsProviderAdapter}:
        adapter = copy.copy(adapter)
        adapter.config = integration.config or {}
    return adapter


def provider_state(integration):
    try:
        adapter = adapter_for(integration)
    except ProviderFailure:
        return "unavailable"
    state = getattr(integration.status, "value", integration.status)
    if state in {"connected", "expired", "error"}:
        return "degraded" if state == "connected" and integration.last_sync_error else state
    try:
        adapter.configuration()
    except ProviderFailure:
        return "unavailable"
    return "configured"
