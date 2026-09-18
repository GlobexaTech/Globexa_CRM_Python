"""Explicit destinations, DNS-pinned TLS, no redirect/retry after an uncertain POST."""
import asyncio
import json
import os
from urllib.parse import urlsplit
from fastapi import HTTPException
from app.services.ai.research import resolve_public, PinnedHTTPSConnection
from app.services.ai.safety import safe_data


class WebhookFailure(Exception):
    def __init__(self, code, *, retryable=False, uncertain=False, retry_after=0):
        self.code, self.retryable, self.uncertain, self.retry_after = code, retryable, uncertain, retry_after
        super().__init__(code)


def validate_destination(url):
    parsed = urlsplit(url)
    hosts = {value.strip().lower() for value in os.environ.get("AUTOMATION_WEBHOOK_ALLOWED_HOSTS", "").split(",") if value.strip()}
    try:
        valid = parsed.scheme == "https" and parsed.hostname in hosts and parsed.port in (None, 443)
    except ValueError:
        valid = False
    if not valid or parsed.username or parsed.password or parsed.query or parsed.fragment or "\\" in url:
        raise HTTPException(422, "Webhook destination must be an administrator-allowed HTTPS host without credentials or query")
    return parsed


def post(url, payload, key):
    parsed = validate_destination(url)
    safe_data(payload)
    body = json.dumps(payload, ensure_ascii=False).encode()
    if len(body) > 24000: raise HTTPException(422, "Webhook payload exceeds limit")
    address = resolve_public(parsed.hostname)
    connection = PinnedHTTPSConnection(parsed.hostname, address)
    try:
        # A timeout here may follow a successful delivery. It is never retried automatically.
        connection.request("POST", parsed.path or "/", body=body,
                           headers={"Content-Type": "application/json", "Idempotency-Key": key})
        response = connection.getresponse()
        response.read(100001)
        if response.status in {429, 503}:
            retry = response.getheader("Retry-After", "0")
            raise WebhookFailure("webhook_rate_limited", retryable=response.status == 429,
                                 uncertain=response.status == 503, retry_after=min(3600, int(retry)) if retry.isdigit() else 0)
        if 300 <= response.status < 400:
            raise WebhookFailure("webhook_redirect_forbidden")
        if not 200 <= response.status < 300: raise WebhookFailure("webhook_rejected", uncertain=response.status >= 500)
        return {"status": "sent", "http_status": response.status}
    except (OSError, TimeoutError) as exc:
        raise WebhookFailure("webhook_outcome_unknown", uncertain=True) from exc
    finally:
        connection.close()


async def deliver(url, payload, key):
    return await asyncio.to_thread(post, url, payload, key)
