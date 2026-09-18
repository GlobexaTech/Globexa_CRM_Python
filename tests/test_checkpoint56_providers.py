"""Executed provider contracts and durable integration tests; no live credentials."""
import base64
import hashlib
import hmac
import json
from datetime import timedelta
from uuid import UUID, uuid4
from urllib.parse import parse_qs, urlsplit
import httpx
import pytest
from sqlalchemy import select, func
from app.core.webhooks import verify_signature, InvalidWebhook
from app.models import (Integration, Message, Conversation, Contact, SyncCursor, SyncJob, OperationJob,
                        WebhookReceipt, WebhookEndpoint, DomainEvent, DeadLetterEvent)
from app.services.crm.providers import (MailAdapter, WhatsAppAdapter, MetaProviderAdapter, InstagramProviderAdapter,
    LinkedInProviderAdapter, GoogleAdsProviderAdapter, ApolloProviderAdapter, ProviderFailure, adapters, adapter_for)
from app.services.crm.provider_pipeline import match_contact, process_receipt, apply_delivery_status
from app.services.crm.jobs import execute_job
from app.services.crm.common import now
from test_checkpoint3 import crm as crm, post


@pytest.mark.parametrize("provider", ["gmail", "outlook", "linkedin", "google_ads"])
async def test_oauth_contract_state_pkce_exchange(provider, monkeypatch):
    for field in ("CLIENT_ID", "CLIENT_SECRET"):
        monkeypatch.setenv(f"CRM_{provider.upper()}_{field}", uuid4().hex)
    monkeypatch.setenv(f"CRM_{provider.upper()}_REDIRECT_URI", "https://crm.example.test/integrations/callback")
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"access_token": uuid4().hex, "expires_in": 3600})
    adapter = MailAdapter(provider, httpx.MockTransport(handler))
    params = parse_qs(urlsplit(adapter.authorization_url("test-state", "challenge")).query)
    assert params["state"] == ["test-state"] and params["code_challenge_method"] == ["S256"]
    await adapter.connect("code", "verifier", "https://crm.example.test/integrations/callback")
    body = parse_qs(calls[0].content.decode())
    assert body["code_verifier"] == ["verifier"] and body["grant_type"] == ["authorization_code"]
    with pytest.raises(ProviderFailure, match="redirect_mismatch"):
        await adapter.connect("code", "verifier", "https://attacker.test")


@pytest.mark.parametrize("status,retry,unknown", [(401, False, False), (429, True, False), (500, False, True), (302, False, False)])
async def test_provider_errors_never_fake_success(status, retry, unknown):
    adapter = MailAdapter("gmail", httpx.MockTransport(lambda request: httpx.Response(status, json={}, headers={"Retry-After": "123"})))
    with pytest.raises(ProviderFailure) as caught:
        await adapter.request("POST", "https://gmail.googleapis.com/test", external_write=True)
    assert caught.value.retryable is retry and caught.value.uncertain is unknown
    assert caught.value.retry_after == 123


async def test_whatsapp_uses_tenant_token_and_unknown_transport(monkeypatch):
    monkeypatch.setenv("CRM_META_GRAPH_VERSION", "v25.0")
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.123"}]})
    adapter = WhatsAppAdapter(httpx.MockTransport(handler), {"phone_number_id": "123"})
    token = uuid4().hex
    result = await adapter.send(token, {"recipient": "+919999999999", "body": "Hello"}, "key")
    assert result == {"provider_message_id": "wamid.123", "status": "sent"}
    assert calls[0].headers["authorization"] == "Bearer " + token
    assert json.loads(calls[0].content)["to"] == "919999999999"
    def timeout(request):
        raise httpx.ReadTimeout("private provider detail")
    adapter.transport = httpx.MockTransport(timeout)
    with pytest.raises(ProviderFailure) as caught:
        await adapter.send(token, {"recipient": "+919999999999", "body": "Hello"}, "key")
    assert caught.value.uncertain and not caught.value.retryable


@pytest.mark.parametrize("adapter,method", [(WhatsAppAdapter(), "sync"), (InstagramProviderAdapter(), "sync"),
    (LinkedInProviderAdapter(), "send"), (LinkedInProviderAdapter(), "sync"), (GoogleAdsProviderAdapter(), "send"),
    (ApolloProviderAdapter(), "sync"), (ApolloProviderAdapter(), "refresh")])
async def test_unsupported_capability_explicit(adapter, method):
    assert method not in adapter.capabilities
    with pytest.raises(ProviderFailure, match="capability_unavailable"):
        await getattr(adapter, method)("token")


async def test_apollo_real_contract_and_no_fabricated_enrichment():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"person": {"id": "person-123", "email_status": "verified", "email": "alice@example.com"}})
    adapter = ApolloProviderAdapter(httpx.MockTransport(handler))
    result = await adapter.enrich(uuid4().hex, {"email": "alice@example.com"})
    assert calls[0].url.path == "/api/v1/people/match" and "x-api-key" in calls[0].headers
    assert result["provider_id"] == "person-123" and result["provider"] == "apollo"
    adapter.transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"person": None}))
    assert (await adapter.enrich("token", {"email": "alice@example.com"}))["status"] == "not_found"
    with pytest.raises(ProviderFailure, match="verified_identity_required"):
        await adapter.enrich("token", {"name": "Alice"})


async def test_apollo_paid_activation_defaults_off(monkeypatch):
    monkeypatch.delenv("CRM_APOLLO_ENRICHMENT_ENABLED", raising=False)
    with pytest.raises(ProviderFailure, match="credit_consuming_operation_disabled"):
        await ApolloProviderAdapter().enrich("token", {"email": "alice@example.com"})


async def test_linkedin_only_supported_oidc_contract():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"sub": "person-1", "email": "alice@example.com"})
    result = await LinkedInProviderAdapter(httpx.MockTransport(handler)).health_check("token")
    assert calls[0].url.path == "/v2/userinfo" and result["provider_account_id"] == "person-1"


async def test_outlook_delta_cursor_and_ssrf_rejected():
    good = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=abc"
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"value": [], "@odata.deltaLink": good})
    adapter = MailAdapter("outlook", httpx.MockTransport(handler))
    result = await adapter.sync("token")
    assert result["cursor"] == good and not result["has_more"]
    await adapter.sync("token", good)
    for cursor in ["http://127.0.0.1/", "https://graph.microsoft.com.evil.test/v1.0/me/mailFolders/inbox/messages/delta", "https://graph.microsoft.com/v1.0/users"]:
        with pytest.raises(ProviderFailure, match="invalid_cursor"):
            await adapter.sync("token", cursor)
    assert len(calls) == 2


async def test_outlook_preserves_provider_message_id():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(201, json={"id": "immutable-123", "conversationId": "thread-1"}) if len(calls) == 1 else httpx.Response(202)
    result = await MailAdapter("outlook", httpx.MockTransport(handler)).send("token", {"recipient": "alice@example.com", "subject": "Hi", "body": "Hello"}, "key")
    assert result["provider_message_id"] == "immutable-123" and result["status"] == "sent"
    assert calls[1].url.path.endswith("/immutable-123/send")


async def test_gmail_initial_then_incremental_sync():
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "100"})
        if request.url.path.endswith("/history"):
            assert request.url.params["startHistoryId"] == "100"
            return httpx.Response(200, json={"historyId": "101", "history": []})
        return httpx.Response(200, json={"messages": []})
    adapter = MailAdapter("gmail", httpx.MockTransport(handler))
    first = await adapter.sync("token")
    second = await adapter.sync("token", first["cursor"])
    assert json.loads(second["cursor"])["history_id"] == "101" and len(calls) == 3


def whatsapp_payload(message_id="wamid.inbound"):
    return {"object": "whatsapp_business_account", "entry": [{"id": "business-1", "changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "123", "display_phone_number": "919000000000"},
        "messages": [{"id": message_id, "from": "919999999999", "timestamp": str(int(now().timestamp())), "type": "text", "text": {"body": "Question"}}]}}]}]}


def test_real_whatsapp_signed_timestamp_and_replay():
    payload = whatsapp_payload()
    secret = uuid4().hex
    body = json.dumps(payload).encode()
    headers = {"x-hub-signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}
    assert verify_signature("whatsapp", secret, body, headers)
    with pytest.raises(InvalidWebhook):
        verify_signature("whatsapp", secret, body, headers, now().timestamp() + 301)
    with pytest.raises(InvalidWebhook):
        verify_signature("whatsapp", secret, body + b" ", headers)


def test_google_ads_official_shared_key_and_event_identity():
    secret = uuid4().hex
    body = json.dumps({"google_key": secret, "lead_id": "lead-123"}).encode()
    assert verify_signature("google_ads", secret, body, {})
    with pytest.raises(InvalidWebhook):
        verify_signature("google_ads", secret, json.dumps({"google_key": secret}).encode(), {})


async def test_tenant_adapter_config_never_leaks():
    a = Integration(type="whatsapp", config={"provider": "whatsapp", "phone_number_id": "111"})
    b = Integration(type="whatsapp", config={"provider": "whatsapp", "phone_number_id": "222"})
    assert adapter_for(a).phone_id() == "111" and adapter_for(b).phone_id() == "222"
    assert adapters["whatsapp"].config == {}


async def test_matching_verified_and_ambiguous_never_names(db_session, crm):
    identity = {"email": crm["contact"].email, "email_verified": True}
    assert (await match_contact(db_session, crm["tenant"], crm["integration"].id, identity))["status"] == "MATCHED"
    assert (await match_contact(db_session, crm["tenant"], crm["integration"].id, {"email": crm["contact"].email}))["status"] == "NEW"
    db_session.add(Contact(tenant_id=crm["tenant"], first_name="Duplicate", last_name="Person", email=crm["contact"].email))
    await db_session.flush()
    result = await match_contact(db_session, crm["tenant"], crm["integration"].id, identity)
    assert result["status"] == "AMBIGUOUS" and result["contact"] is None
    assert (await match_contact(db_session, crm["tenant"], crm["integration"].id, {"name": "Alice Customer"}))["status"] == "NEW"


async def test_sync_cursor_server_only_atomic_pagination_and_cancel(client, db_session, crm):
    response = await post(client, crm, f"/operations/integrations/{crm['integration'].id}/sync?cursor=attacker")
    assert response.status_code == 422
    calls = []
    async def sync(token, cursor=None):
        calls.append(cursor)
        return {"messages": [], "cursor": "next-page", "has_more": True}
    crm["mock"].sync = sync
    response = await post(client, crm, f"/operations/integrations/{crm['integration'].id}/sync", key="sync-page-key")
    assert response.status_code == 202, response.text
    job = await execute_job(db_session, crm["tenant"], UUID(response.json()["id"]))
    assert job.status == "retry"
    cursor = await db_session.scalar(select(SyncCursor))
    assert cursor.cursor_value == "next-page" and calls == [None]
    sync_id = UUID(job.result["sync_job_id"])
    response = await post(client, crm, f"/integrations/sync-jobs/{sync_id}/cancel")
    assert response.status_code == 200, response.text
    job.available_at = now() - timedelta(seconds=1)
    await db_session.flush()
    await execute_job(db_session, crm["tenant"], job.id)
    assert job.status == "cancelled" and len(calls) == 1


async def test_sync_does_not_advance_cursor_on_failed_persistence(client, db_session, crm):
    async def sync(token, cursor=None):
        return {"messages": [{"provider_message_id": "invalid"}], "cursor": "must-not-save", "has_more": False}
    crm["mock"].sync = sync
    response = await post(client, crm, f"/operations/integrations/{crm['integration'].id}/sync")
    job = await execute_job(db_session, crm["tenant"], UUID(response.json()["id"]))
    assert job.status == "failed"
    assert await db_session.scalar(select(func.count()).select_from(SyncCursor)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Message)) == 0


async def make_receipt(db_session, crm, payload):
    integration = Integration(tenant_id=crm["tenant"], name="WhatsApp", type="whatsapp", status="connected", created_by_id=crm["user"],
                              config={"provider": "whatsapp", "phone_number_id": "123"})
    db_session.add(integration)
    await db_session.flush()
    endpoint = WebhookEndpoint(tenant_id=crm["tenant"], integration_id=integration.id, name="Inbound", url_path="/unique", secret=uuid4().hex,
                               events=["message.received"], max_retries=3)
    event = DomainEvent(tenant_id=crm["tenant"], event_type="webhook.received", aggregate_id=str(integration.id), idempotency_key=uuid4().hex)
    db_session.add_all([endpoint, event])
    await db_session.flush()
    receipt = WebhookReceipt(tenant_id=crm["tenant"], webhook_id=endpoint.id, event_id=event.id,
                             digest=hashlib.sha256(json.dumps(payload).encode()).hexdigest(), payload=payload)
    db_session.add(receipt)
    await db_session.flush()
    return receipt, integration, endpoint


async def test_whatsapp_webhook_normalizes_once_and_domain_event(db_session, crm):
    receipt, integration, endpoint = await make_receipt(db_session, crm, whatsapp_payload())
    await process_receipt(db_session, crm["tenant"], receipt.id)
    assert receipt.state == "completed" and receipt.payload == {}
    message = await db_session.scalar(select(Message))
    conversation = await db_session.scalar(select(Conversation))
    assert message.provider_message_id == "wamid.inbound" and conversation.channel == "whatsapp"
    await process_receipt(db_session, crm["tenant"], receipt.id)
    assert await db_session.scalar(select(func.count()).select_from(Message)) == 1
    assert await db_session.scalar(select(func.count()).select_from(DomainEvent).where(DomainEvent.event_type == "message.received")) == 1


async def test_wrong_account_and_unsupported_webhook_dead_letter(db_session, crm):
    payload = whatsapp_payload()
    payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "another-tenant"
    receipt, _, _ = await make_receipt(db_session, crm, payload)
    await process_receipt(db_session, crm["tenant"], receipt.id)
    assert receipt.state == "dead_letter" and receipt.error_code == "webhook_account_mismatch"
    assert await db_session.scalar(select(func.count()).select_from(Message)) == 0
    assert await db_session.scalar(select(func.count()).select_from(DeadLetterEvent)) == 1


async def test_delivery_status_monotonic_and_sent_distinct(db_session, crm):
    conversation = Conversation(tenant_id=crm["tenant"], integration_id=crm["integration"].id, subject="Delivery")
    db_session.add(conversation)
    await db_session.flush()
    message = Message(tenant_id=crm["tenant"], conversation_id=conversation.id, body="Sent", direction="outbound", status="sent", provider_message_id="outbound-1")
    db_session.add(message)
    await db_session.flush()
    assert message.status != "delivered"
    for status in ["delivered", "sent", "failed", "read"]:
        await apply_delivery_status(db_session, crm["tenant"], crm["integration"].id, {"provider_message_id": "outbound-1", "status": status})
    assert message.status == "read"


async def test_meta_lead_sync_and_signed_webhook_contract(monkeypatch):
    monkeypatch.setenv("CRM_META_GRAPH_VERSION", "v25.0")
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [{"id": "lead-1", "created_time": now().isoformat(), "field_data": [
            {"name": "email", "values": ["alice@example.com"]}, {"name": "full_name", "values": ["Alice"]}]}],
            "paging": {"next": "https://graph.facebook.com/v25.0/123/leads?after=abc", "cursors": {"after": "abc"}}})
    adapter = MetaProviderAdapter(httpx.MockTransport(handler), config={"form_id": "123"})
    result = await adapter.sync("token")
    assert calls[0].url.path == "/v25.0/123/leads" and result["has_more"]
    assert result["leads"][0]["provider_id"] == "lead-1" and not result["leads"][0]["email_verified"]
    event = (await adapter.handle_webhook({"entry": [{"changes": [{"field": "leadgen", "value": {
        "page_id": "page-1", "leadgen_id": "lead-1", "created_time": int(now().timestamp())}}]}]}))[0]
    assert event["kind"] == "lead_reference" and event["account_id"] == "page-1"


async def test_instagram_inbound_contract_does_not_claim_send():
    result = await InstagramProviderAdapter().handle_webhook({"entry": [{"id": "page-1", "messaging": [{
        "timestamp": int(now().timestamp() * 1000), "sender": {"id": "person-1"}, "recipient": {"id": "page-1"},
        "message": {"mid": "message-1", "text": "Hello"}}]}]})
    assert result[0]["message"]["channel"] == "social" and "send" not in InstagramProviderAdapter.capabilities


async def test_google_ads_official_fields_pagination_incremental(monkeypatch):
    monkeypatch.setenv("CRM_GOOGLE_ADS_API_VERSION", "v24")
    monkeypatch.setenv("CRM_GOOGLE_ADS_DEVELOPER_TOKEN", uuid4().hex)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"results": [{"leadFormSubmissionData": {"id": "lead-1", "submissionDateTime": now().isoformat(),
            "leadFormSubmissionFields": [{"fieldType": "EMAIL", "fieldValue": "alice@example.com"}]}}]})
    adapter = GoogleAdsProviderAdapter(httpx.MockTransport(handler), {"customer_id": "123-456-7890"})
    result = await adapter.sync("token")
    assert result["leads"][0]["email"] == "alice@example.com"
    await adapter.sync("token", result["cursor"])
    assert "WHERE lead_form_submission_data.submission_date_time >=" in json.loads(calls[1].content)["query"]
    assert calls[0].url.path == "/v24/customers/1234567890/googleAds:search"
    assert "developer-token" in calls[0].headers


async def test_webhook_ingress_duplicate_tamper_and_real_worker(client, db_session, crm):
    receipt, integration, endpoint = await make_receipt(db_session, crm, whatsapp_payload("seed"))
    payload = whatsapp_payload("fresh-inbound")
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(endpoint.secret.encode(), body, hashlib.sha256).hexdigest()
    response = await client.post(f"/api/v1/hooks/{endpoint.id}", content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})
    assert response.status_code == 202, response.text
    received_id = UUID(response.json()["receipt_id"])
    response = await client.post(f"/api/v1/hooks/{endpoint.id}", content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})
    assert response.json()["status"] == "duplicate"
    job = await db_session.scalar(select(OperationJob).where(OperationJob.kind == "provider_webhook"))
    await execute_job(db_session, crm["tenant"], job.id)
    assert job.status == "completed"
    saved = await db_session.get(WebhookReceipt, received_id)
    assert saved.state == "completed"
    assert await db_session.scalar(select(func.count()).select_from(Message)) == 1
    # An alternate JSON serialization bypasses body digest dedupe but not provider-id dedupe.
    body2 = json.dumps(payload, indent=2).encode()
    signature2 = "sha256=" + hmac.new(endpoint.secret.encode(), body2, hashlib.sha256).hexdigest()
    response = await client.post(f"/api/v1/hooks/{endpoint.id}", content=body2,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature2})
    assert response.status_code == 202
    job2 = await db_session.scalar(select(OperationJob).where(OperationJob.kind == "provider_webhook", OperationJob.id != job.id))
    await execute_job(db_session, crm["tenant"], job2.id)
    assert await db_session.scalar(select(func.count()).select_from(Message)) == 1


async def test_configure_checks_health_and_only_selected_credential_active(client, db_session, crm, monkeypatch):
    from app.models import IntegrationCredential
    integration = Integration(tenant_id=crm["tenant"], name="Apollo", type="apollo", status="pending", created_by_id=crm["user"], config={"provider": "apollo"})
    db_session.add(integration)
    await db_session.flush()
    adapter = ApolloProviderAdapter(httpx.MockTransport(lambda request: httpx.Response(200, json={"is_logged_in": True})))
    monkeypatch.setitem(adapters, "apollo", adapter)
    ids = []
    for name in ["first", "second"]:
        response = await post(client, crm, f"/integrations/{integration.id}/credentials", {"name": name, "credentials": {"api_key": uuid4().hex}})
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    assert integration.status.value == "pending"
    response = await post(client, crm, f"/integrations/{integration.id}/configure", {"credential_id": ids[-1]})
    assert response.status_code == 200 and response.json()["status"] == "connected", response.text
    credentials = (await db_session.scalars(select(IntegrationCredential).where(IntegrationCredential.integration_id == integration.id))).all()
    assert [str(item.id) for item in credentials if item.is_active] == [ids[-1]]
    adapter.transport = httpx.MockTransport(lambda request: httpx.Response(401, json={}))
    response = await post(client, crm, f"/integrations/{integration.id}/configure", {"credential_id": ids[-1]})
    assert response.status_code >= 400


async def test_whatsapp_outbound_requires_recent_inbound_window(client, db_session, crm, monkeypatch):
    from app.models import OAuthToken
    monkeypatch.setenv("CRM_META_GRAPH_VERSION", "v25.0")
    receipt, integration, _ = await make_receipt(db_session, crm, whatsapp_payload())
    await process_receipt(db_session, crm["tenant"], receipt.id)
    db_session.add(OAuthToken(tenant_id=crm["tenant"], integration_id=integration.id, access_token=uuid4().hex, expires_at=now() + timedelta(hours=1)))
    await db_session.flush()
    conversation = await db_session.scalar(select(Conversation))
    adapter = WhatsAppAdapter(httpx.MockTransport(lambda request: httpx.Response(200, json={"messages": [{"id": "wamid.outbound"}]})))
    monkeypatch.setitem(adapters, "whatsapp", adapter)
    response = await post(client, crm, f"/operations/conversations/{conversation.id}/messages", {"recipient": "+919999999999", "body": "We can help"})
    assert response.status_code == 202, response.text
    job = await execute_job(db_session, crm["tenant"], UUID(response.json()["id"]))
    assert job.status == "completed"
    outbound = await db_session.scalar(select(Message).where(Message.direction == "outbound"))
    assert outbound.status == "sent" and outbound.provider_message_id == "wamid.outbound"
    inbound = await db_session.scalar(select(Message).where(Message.direction == "inbound"))
    inbound.occurred_at = now() - timedelta(days=2)
    await db_session.flush()
    response = await post(client, crm, f"/operations/conversations/{conversation.id}/messages", {"recipient": "+919999999999", "body": "Old window"}, key="new-outside-window")
    assert response.status_code == 409


async def test_public_webhook_rejects_tamper_and_audits_safely(client, db_session, crm):
    from app.models import AuditLog
    _, _, endpoint = await make_receipt(db_session, crm, whatsapp_payload("seed"))
    response = await client.post(f"/api/v1/hooks/{endpoint.id}", content=json.dumps(whatsapp_payload()).encode(),
        headers={"X-Hub-Signature-256": "sha256=" + "0" * 64, "Content-Type": "application/json"})
    assert response.status_code == 401 and "traceback" not in response.text.lower()
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "webhook.failed")) == 1
    assert await db_session.scalar(select(func.count()).select_from(Message)) == 0


async def test_meta_subscription_challenge_requires_separate_verify_token(client, db_session, crm):
    _, _, endpoint = await make_receipt(db_session, crm, whatsapp_payload())
    token = uuid4().hex
    endpoint.custom_fields = {"verify_token_hash": hashlib.sha256(token.encode()).hexdigest()}
    await db_session.flush()
    response = await client.get(f"/api/v1/hooks/{endpoint.id}", params={"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "123456"})
    assert response.status_code == 200 and response.text == "123456"
    response = await client.get(f"/api/v1/hooks/{endpoint.id}", params={"hub.mode": "subscribe", "hub.verify_token": endpoint.secret, "hub.challenge": "123456"})
    assert response.status_code == 401


async def test_sync_reset_initial_and_active_job_conflict(client, db_session, crm):
    db_session.add(SyncCursor(tenant_id=crm["tenant"], integration_id=crm["integration"].id, cursor_type="provider", cursor_value="expired-history"))
    await db_session.flush()
    response = await post(client, crm, f"/integrations/{crm['integration'].id}/sync-reset")
    assert response.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(SyncCursor)) == 0
    response = await post(client, crm, f"/operations/integrations/{crm['integration'].id}/sync")
    assert response.status_code == 202
    row = await db_session.scalar(select(SyncJob))
    assert row.sync_type == "initial"
    response = await post(client, crm, f"/integrations/{crm['integration'].id}/sync-reset")
    assert response.status_code == 409


async def test_provider_webhook_rate_limit_checked_after_duplicate(client, db_session, crm):
    _, _, endpoint = await make_receipt(db_session, crm, whatsapp_payload("seed"))
    endpoint.rate_limit_per_minute = 1
    await db_session.flush()
    body = json.dumps(whatsapp_payload("fresh")).encode()
    signature = "sha256=" + hmac.new(endpoint.secret.encode(), body, hashlib.sha256).hexdigest()
    response = await client.post(f"/api/v1/hooks/{endpoint.id}", content=body,
        headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"})
    assert response.status_code == 429 and response.headers["retry-after"] == "60"


async def test_whatsapp_cannot_reuse_other_recipient_service_window(client, db_session, crm):
    receipt, integration, _ = await make_receipt(db_session, crm, whatsapp_payload())
    await process_receipt(db_session, crm["tenant"], receipt.id)
    conversation = await db_session.scalar(select(Conversation))
    response = await post(client, crm, f"/operations/conversations/{conversation.id}/messages", {"recipient": "+918888888888", "body": "Wrong person"})
    assert response.status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(Message).where(Message.direction == "outbound")) == 0


from test_rls import isolated_rls as isolated_rls


async def test_concurrent_webhook_duplicates_use_restricted_independent_connections(isolated_rls, monkeypatch):
    import asyncio
    from cryptography.fernet import Fernet
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.core.config import get_settings
    from app.core.database import get_db
    from app.core.tenant_context import tenant_context
    from app.main import app
    from app.models import Participant
    factory, tenants, users, integrations, _ = isolated_rls
    monkeypatch.setattr(get_settings().security, "credential_encryption_key", Fernet.generate_key().decode())
    runtime = create_async_engine(factory.kw["bind"].url, pool_size=3, max_overflow=0)
    concurrent = async_sessionmaker(runtime, expire_on_commit=False)
    admin = create_async_engine(get_settings().database.url, poolclass=NullPool)
    secret = uuid4().hex
    endpoint_id = uuid4()
    async def request_db():
        async with concurrent() as db:
            yield db
    previous = app.dependency_overrides.get(get_db)
    try:
        with tenant_context(tenants[0], users[0]):
            async with concurrent() as db:
                integration = await db.get(Integration, integrations[0])
                integration.type = "whatsapp"
                integration.config = {"provider": "whatsapp", "phone_number_id": "123"}
                db.add(WebhookEndpoint(id=endpoint_id, tenant_id=tenants[0], integration_id=integrations[0], name="Concurrent", url_path="/concurrent", secret=secret))
                await db.commit()
        app.dependency_overrides[get_db] = request_db
        body = json.dumps(whatsapp_payload()).encode()
        headers = {"X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), "Content-Type": "application/json"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            results = await asyncio.gather(*(client.post(f"/api/v1/hooks/{endpoint_id}", content=body, headers=headers) for _ in range(3)))
        assert [r.status_code for r in results] == [202, 202, 202]
        assert sorted(r.json()["status"] for r in results) == ["accepted", "duplicate", "duplicate"]
        with tenant_context(tenants[0], users[0]):
            async with concurrent() as db:
                assert await db.scalar(select(func.count()).select_from(WebhookReceipt)) == 1
                jobs = (await db.scalars(select(OperationJob).where(OperationJob.kind == "provider_webhook"))).all()
                assert len(jobs) == 1
                await execute_job(db, tenants[0], jobs[0].id)
                assert await db.scalar(select(func.count()).select_from(Message)) == 1
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        await runtime.dispose()
        async with admin.begin() as db:
            for model in (Participant, Message, Conversation, OperationJob, WebhookReceipt, WebhookEndpoint):
                await db.execute(delete(model).where(model.tenant_id.in_(tenants)))
        await admin.dispose()


@pytest.mark.parametrize("mutation,expected", [("disconnect", 409), ("reconfigure", 409), ("revoke", 403)])
async def test_oauth_exchange_cannot_resurrect_changed_integration(isolated_rls, monkeypatch, mutation, expected):
    import asyncio
    from types import SimpleNamespace
    from cryptography.fernet import Fernet
    from fastapi import HTTPException
    from sqlalchemy import delete, update
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.core.config import get_settings
    from app.core.tenant_context import tenant_context
    from app.models import OAuthSession, OAuthToken, Membership, AuditLog, IntegrationStatusEnum
    from app.services.crm.integrations import finish_oauth, disconnect
    factory, tenants, users, integrations, _ = isolated_rls
    monkeypatch.setattr(get_settings().security, "credential_encryption_key", Fernet.generate_key().decode())
    for suffix in ("CLIENT_ID", "CLIENT_SECRET"):
        monkeypatch.setenv("CRM_GMAIL_" + suffix, uuid4().hex)
    monkeypatch.setenv("CRM_GMAIL_REDIRECT_URI", "https://crm.example.test/integrations/callback")
    entered, release = asyncio.Event(), asyncio.Event()
    async def exchange(request):
        assert request.url.path == "/token"
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"access_token": uuid4().hex, "expires_in": 3600})
    monkeypatch.setitem(adapters, "gmail", MailAdapter("gmail", httpx.MockTransport(exchange)))
    state = uuid4().hex
    admin = create_async_engine(get_settings().database.url, poolclass=NullPool)
    try:
        with tenant_context(tenants[0], users[0]):
            async with factory() as db:
                integration = await db.get(Integration, integrations[0])
                integration.config = {"provider": "gmail"}
                integration.status = IntegrationStatusEnum.PENDING
                db.add(OAuthSession(tenant_id=tenants[0], actor_id=users[0], integration_id=integrations[0],
                    state_hash=hashlib.sha256(state.encode()).hexdigest(), verifier=uuid4().hex,
                    redirect_uri="https://crm.example.test/integrations/callback", expires_at=now()+timedelta(minutes=10)))
                await db.commit()
            async def callback():
                async with factory() as db:
                    # Retain this object to expose stale ORM identity-map authorization.
                    cached = await db.scalar(select(Membership).where(Membership.user_id == users[0]))
                    assert cached.role.value == "owner"
                    with pytest.raises(HTTPException) as error:
                        await finish_oauth(db, tenants[0], users[0], integrations[0], SimpleNamespace(state=state, code="authorization-code"))
                    assert error.value.status_code == expected
            pending = asyncio.create_task(callback())
            await asyncio.wait_for(entered.wait(), 5)
            async with factory() as db:
                if mutation == "disconnect":
                    await disconnect(db, tenants[0], users[0], integrations[0])
                elif mutation == "reconfigure":
                    await db.execute(update(Integration).where(Integration.id == integrations[0]).values(config={"provider": "outlook"}))
                else:
                    await db.execute(update(Membership).where(Membership.user_id == users[0]).values(role="viewer"))
                await db.commit()
            release.set()
            await asyncio.wait_for(pending, 10)
            async with factory() as db:
                assert await db.scalar(select(func.count()).select_from(OAuthToken)) == 0
                integration = await db.get(Integration, integrations[0])
                assert integration.status != IntegrationStatusEnum.CONNECTED
    finally:
        release.set()
        async with admin.begin() as db:
            for model in (AuditLog, OAuthToken, OAuthSession):
                await db.execute(delete(model).where(model.tenant_id.in_(tenants)))
        await admin.dispose()


@pytest.mark.parametrize("provider,payload", [("whatsapp", {"entry": "bad"}), ("whatsapp", {"entry": [{"changes": [{"value": []}]}]}), ("google_ads", []), ("whatsapp", {"entry": [{"time": float("inf")}]})])
def test_malformed_signed_webhook_payload_fails_closed(provider, payload):
    body = json.dumps(payload).encode()
    secret = uuid4().hex
    headers = {"X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}
    with pytest.raises(InvalidWebhook):
        verify_signature(provider, secret, body, headers)


@pytest.mark.parametrize("uri", ["https://", "https://user:password@crm.example.test/callback", "https://crm.example.test/callback#fragment", "https://crm.example.test:bad/callback"])
def test_oauth_redirect_configuration_requires_valid_https_origin(uri, monkeypatch):
    for suffix in ("CLIENT_ID", "CLIENT_SECRET"):
        monkeypatch.setenv("CRM_GMAIL_" + suffix, uuid4().hex)
    monkeypatch.setenv("CRM_GMAIL_REDIRECT_URI", uri)
    with pytest.raises(ProviderFailure, match="oauth_not_configured"):
        MailAdapter("gmail").configuration()


async def test_credentials_validate_iso_expiry_and_never_echo_secret(client, db_session, crm):
    from app.models import IntegrationCredential
    path = f"/integrations/{crm['integration'].id}/credentials"
    response = await post(client, crm, path, {"name": "ISO token", "credentials": {"api_key": uuid4().hex}, "token_expires_at": "2030-01-01T00:00:00Z"})
    assert response.status_code == 201
    credential = await db_session.get(IntegrationCredential, UUID(response.json()["id"]))
    assert credential.token_expires_at.year == 2030 and credential.token_expires_at.tzinfo
    secret = uuid4().hex
    for invalid in ({"name": "Bad expiry", "credentials": {"api_key": secret}, "token_expires_at": secret},
                    {"name": "Nested", "credentials": {"api_key": {"private": secret}}},
                    {"name": "Unencrypted", "custom_fields": {"api_key": secret}}):
        response = await post(client, crm, path, invalid)
        assert response.status_code == 422 and secret not in response.text


async def test_apollo_lead_enrichment_persists_actual_provenance(client, db_session, crm, monkeypatch):
    from app.models import Lead
    from app.services.crm.integrations import store_tokens
    integration = crm["integration"]
    integration.config = {"provider": "apollo"}
    contact = await db_session.scalar(select(Contact))
    lead = Lead(tenant_id=crm["tenant"], title="Research prospect", contact_id=contact.id)
    db_session.add(lead)
    await db_session.flush()
    await store_tokens(db_session, crm["tenant"], integration, {"access_token": uuid4().hex})
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.params["email"] == contact.email
        return httpx.Response(200, json={"person": {"id": "apollo-person-1", "email": contact.email, "email_status": "verified", "title": "Engineer"}})
    monkeypatch.setitem(adapters, "apollo", ApolloProviderAdapter(httpx.MockTransport(handler)))
    response = await post(client, crm, f"/integrations/{integration.id}/enrich", {"lead_id": str(lead.id)})
    assert response.status_code == 200 and len(calls) == 1
    assert lead.custom_fields["enrichment"]["provider_id"] == "apollo-person-1"
    assert contact.custom_fields["enrichment"]["provider"] == "apollo"
    response = await post(client, crm, f"/integrations/{integration.id}/enrich", {"lead_id": str(lead.id), "contact_id": str(contact.id)})
    assert response.status_code == 422 and len(calls) == 1


async def test_message_send_revocation_during_token_refresh_prevents_external_send(isolated_rls, monkeypatch):
    import asyncio
    from cryptography.fernet import Fernet
    from sqlalchemy import delete, update
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.core.config import get_settings
    from app.core.tenant_context import tenant_context
    from app.models import OAuthToken, Membership, AuditLog, IntegrationStatusEnum
    factory, tenants, users, integrations, _ = isolated_rls
    monkeypatch.setattr(get_settings().security, "credential_encryption_key", Fernet.generate_key().decode())
    for suffix in ("CLIENT_ID", "CLIENT_SECRET"):
        monkeypatch.setenv("CRM_GMAIL_" + suffix, uuid4().hex)
    monkeypatch.setenv("CRM_GMAIL_REDIRECT_URI", "https://crm.example.test/integrations/callback")
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []
    async def provider(request):
        if request.url.path == "/token":
            entered.set()
            await release.wait()
            return httpx.Response(200, json={"access_token": uuid4().hex, "expires_in": 3600})
        sent.append(request)
        return httpx.Response(200, json={"id": "provider-sent", "threadId": "thread"})
    monkeypatch.setitem(adapters, "gmail", MailAdapter("gmail", httpx.MockTransport(provider)))
    runtime = create_async_engine(factory.kw["bind"].url, pool_size=2, max_overflow=0)
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    admin = create_async_engine(get_settings().database.url, poolclass=NullPool)
    job_id, conversation_id = uuid4(), uuid4()
    try:
        with tenant_context(tenants[0], users[0]):
            async with sessions() as db:
                integration = await db.get(Integration, integrations[0])
                integration.config, integration.status = {"provider": "gmail"}, IntegrationStatusEnum.CONNECTED
                db.add(OAuthToken(tenant_id=tenants[0], integration_id=integration.id, access_token=uuid4().hex,
                                 refresh_token=uuid4().hex, expires_at=now()-timedelta(minutes=1)))
                db.add(Conversation(id=conversation_id, tenant_id=tenants[0], integration_id=integration.id, subject="Queued", channel="email"))
                db.add(OperationJob(id=job_id, tenant_id=tenants[0], actor_id=users[0], kind="message_send", idempotency_key=uuid4().hex,
                    payload={"integration_id": str(integration.id), "conversation_id": str(conversation_id), "recipient": "customer@example.com", "body": "Exact text", "subject": "Queued", "thread_id": None}))
                await db.flush()
                db.add(Message(tenant_id=tenants[0], conversation_id=conversation_id, body="Exact text", direction="outbound", status="queued", recipient="customer@example.com", idempotency_key="job:"+str(job_id)))
                await db.commit()
            async def worker():
                async with sessions() as db:
                    cached = await db.scalar(select(Membership).where(Membership.user_id == users[0]))
                    assert cached.role.value == "owner"
                    await execute_job(db, tenants[0], job_id)
                    job = await db.get(OperationJob, job_id)
                    assert job.status == "failed"
            pending = asyncio.create_task(worker())
            await asyncio.wait_for(entered.wait(), 5)
            async with sessions() as db:
                await db.execute(update(Membership).where(Membership.user_id == users[0]).values(role="viewer"))
                await db.commit()
            release.set()
            await asyncio.wait_for(pending, 10)
            assert sent == []
            async with sessions() as db:
                message = await db.scalar(select(Message).where(Message.idempotency_key == "job:"+str(job_id)))
                assert message.status == "failed"
    finally:
        release.set()
        await runtime.dispose()
        async with admin.begin() as db:
            for model in (AuditLog, Message, Conversation, OperationJob, OAuthToken):
                await db.execute(delete(model).where(model.tenant_id.in_(tenants)))
        await admin.dispose()
