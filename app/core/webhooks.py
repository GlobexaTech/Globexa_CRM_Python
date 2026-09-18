"""Raw-body signature verification. Provider timestamps must be signed."""
import hashlib
import hmac
import json
import time


class InvalidWebhook(ValueError):
    pass


def verify_signature(provider: str, secret: str, body: bytes, headers, now=None) -> str:
    if not secret or len(body) > 1_048_576:
        raise InvalidWebhook("Invalid webhook")
    now = time.time() if now is None else now
    headers = {key.lower(): value for key, value in headers.items()}
    if provider in {"meta", "facebook", "instagram", "whatsapp"}:
        supplied = headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, supplied):
            raise InvalidWebhook("Invalid signature")
        # Meta signs the body, not arbitrary headers. Validate each signed entry time.
        try:
            payload = json.loads(body)
            timestamps = []
            for entry in payload["entry"]:
                if "time" in entry:
                    timestamps.append(int(entry["time"]))
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if change.get("field") == "leadgen":
                        timestamps.append(int(value["created_time"]))
                    for item in value.get("messages", []) + value.get("statuses", []):
                        timestamps.append(int(item["timestamp"]))
                for item in entry.get("messaging", []):
                    timestamps.append(int(item["timestamp"]) // 1000)
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            raise InvalidWebhook("Signed timestamp required") from None
        if not timestamps or any(abs(now - stamp) > 300 for stamp in timestamps):
            raise InvalidWebhook("Expired webhook")
    elif provider == "google_ads":
        try:
            payload = json.loads(body)
            if not isinstance(payload.get("google_key"), str) or not hmac.compare_digest(secret, payload["google_key"]):
                raise InvalidWebhook("Invalid key")
            if not isinstance(payload.get("lead_id"), str) or not payload["lead_id"]:
                raise InvalidWebhook("Event identity required")
        except (TypeError, ValueError, KeyError, AttributeError, OverflowError):
            raise InvalidWebhook("Invalid payload") from None
        # Official Google Ads form callbacks contain no authenticated timestamp.
        # Permanent lead-id dedupe (not a fictional signature) prevents replay effects.
    elif provider in {"generic", "webhook", "stripe"}:
        try:
            if provider == "stripe":
                parts = [part.split("=", 1) for part in headers.get("stripe-signature", "").split(",")]
                stamp = next(value for key, value in parts if key == "t")
                signatures = [value for key, value in parts if key == "v1"]
            else:
                stamp = headers["x-webhook-timestamp"]
                signatures = [headers["x-webhook-signature"].removeprefix("sha256=")]
            if abs(now - int(stamp)) > 300:
                raise InvalidWebhook("Expired webhook")
        except (KeyError, ValueError, StopIteration):
            raise InvalidWebhook("Signed timestamp required") from None
        expected = hmac.new(secret.encode(), stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, signature) for signature in signatures):
            raise InvalidWebhook("Invalid signature")
    else:
        raise InvalidWebhook("Unsupported webhook provider")
    return hashlib.sha256(body).hexdigest()
