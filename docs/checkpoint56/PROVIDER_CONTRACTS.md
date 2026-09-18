# Checkpoint 5 provider contracts and evidence

The production adapters use official HTTPS endpoints. Tests replace only the external HTTP transport with deterministic `httpx.MockTransport` responses; they do not replace authorization, tenant/RLS checks, receipt persistence, CRM normalization, operation jobs or delivery-state storage. No live provider account was used and no paid feature was activated.

## Stable OAuth callback

Gmail and Outlook authorization starts at `POST /api/v1/operations/integrations/{integration_id}/authorize` behind an authenticated tenant membership and `integrations:write` permission. The returned URL binds a single-use hashed state, encrypted PKCE verifier, actor, tenant, integration and configured redirect URI. Callback exchange consumes state before the external request and stores encrypted tokens.

**Gmail browser callback route:** `/integrations/callback`.

**Exact Gmail redirect URI format:** `https://<frontend-origin>/integrations/callback`, supplied in `CRM_GMAIL_REDIRECT_URI` and registered identically in Google Cloud. The code does not manufacture a redirect URI. Outlook and the other OAuth adapters use the same frontend callback route with their own `CRM_<PROVIDER>_REDIRECT_URI` values.

**Authenticated backend exchange route:** `POST /api/v1/operations/integrations/{integration_id}/callback`, JSON `{state, code}`. The browser never receives provider tokens. Disconnect removes locally stored access, refresh and pending OAuth state. Gmail/Google OAuth attempt documented token revocation; providers without a delegated revocation operation report `remote_revocation: false` and remove local access.

## Provider capability scope

| Provider | Implemented contract | Explicit limits | Live certification |
|---|---|---|---|
| Gmail | OAuth state/S256 PKCE, encrypted token exchange/refresh, profile health, full inbox page ingestion, history-ID incremental sync, MIME send with provider message/thread IDs | No outbound file upload or push/PubSub subscription; incremental history expiry can be recovered using authenticated sync reset | BLOCKED — Google credential required |
| Outlook | OAuth state/S256 PKCE, encrypted refresh, Graph health, inbox delta/next links, immutable-ID draft creation followed by send | Delegated `Mail.ReadWrite` and `Mail.Send` are required; successful send acceptance means SENT, never DELIVERED | BLOCKED — Microsoft credential required |
| WhatsApp | Tenant-specific encrypted bearer token, phone-ID health, text send, signed inbound messages/statuses, Meta verification challenge, replay window, idempotent normalization, durable retry/dead letter | Free-form send requires the same recipient's inbound message within 24 hours, checked at enqueue and execution; templates, media uploads and historical inbox export are unsupported | BLOCKED — Meta/WhatsApp credential required |
| Meta | OAuth state, account health, Lead Ads form pagination/incremental watermark, signed lead references fetched from Graph, normalization/source IDs; signed social text ingress | Scope approval and configured page/form ownership are live prerequisites; arbitrary messaging and automatic token-refresh are not advertised | BLOCKED — Meta credential required |
| Instagram | Facebook Login authorization contract, signed messaging normalization and configured account mapping through Meta Webhooks | Historical inbox export, arbitrary outbound messaging and token-refresh are not advertised | BLOCKED — Meta/Instagram credential required |
| LinkedIn | Official OIDC OAuth and `/v2/userinfo` health; local disconnect | OIDC is not identity verification. Messaging, lead-gen export, partner-only refresh and webhooks are unavailable and raise explicit capability errors | BLOCKED — LinkedIn credential required |
| Google Ads | OAuth/refresh, developer-token/customer-scoped GAQL read, lead-submission page sync with overlapping date watermark, official form-webhook shared-key validation and provider lead-ID deduplication | No campaign mutation or ad purchases. Google Ads does not sign webhook timestamps; the implementation does not invent one | BLOCKED — Google Ads credential required |
| Apollo | X-Api-Key health, email/provider-ID enrichment, provider IDs, provenance, explicit not-found, rate-limit retry metadata | Enrichment may consume provider credits and is **disabled by default** (`CRM_APOLLO_ENRICHMENT_ENABLED=false`). No automatic paid activation, names-only enrichment, phone reveal, waterfall enrichment or unsigned asynchronous webhooks | BLOCKED — Apollo credential required |

`IMPLEMENTED` and `PROVIDER-READY` refer only to the capability set above. Unsupported operations raise `capability_unavailable`; they never return empty fake success. Provider configuration status is distinct from live certification. Account permission, app review and provider quota entitlement cannot be certified with a test double.

## Configuration and tenant boundaries

Use `CRM_{GMAIL,OUTLOOK,META,INSTAGRAM,LINKEDIN,GOOGLE_ADS}_{CLIENT_ID,CLIENT_SECRET,REDIRECT_URI}` for server application OAuth configuration. `CRM_META_GRAPH_VERSION` and `CRM_GOOGLE_ADS_API_VERSION` are explicit version selectors; `CRM_GOOGLE_ADS_DEVELOPER_TOKEN` remains server-side. Tests use versions v25.0/v24 respectively; operators must select a supported version for their registered applications.

Provider IDs (`phone_number_id`, `business_account_id`, `page_id`, `form_id`, `customer_id`) belong in the tenant integration configuration. Access/API tokens belong only in the encrypted credential endpoint. A stored credential is PENDING until `/integrations/{id}/configure` performs a successful provider health check. Rotation invalidates health status and successful activation deactivates previous credentials. No global WhatsApp token is substituted for a tenant token.

Meta subscriptions use `GET /api/v1/hooks/{endpoint_id}` with a separate verify token whose hash is stored. `POST` verifies raw-body HMAC before binding tenant data access. WhatsApp timestamps come from signed message/status fields, not an invented `entry.time`. Signed entries older than five minutes are rejected by the configured security contract; operators must reconcile delayed provider redelivery operationally. Google Ads uses its official `google_key` and stable `lead_id` because its contract has no signed timestamp. The shared key is removed before receipt storage.

Webhook request size is limited to 1 MiB. Endpoint locking serializes concurrent receipts, body digests prevent identical retries, and provider identity/advisory locks prevent different JSON serializations from creating duplicate CRM messages/leads. A durable operation normalizes receipts into CRM records. Only actual CRM mutations emit `message.received`/`lead.created`; receipt ingress emits `webhook.received`. Payloads are cleared after completion or dead-letter classification. Dead-letter rows retain safe receipt IDs and error codes. Receipt states are pending, processing, completed, failed and dead_letter.

## Sync and communications

Initial sync starts without a server cursor. Incremental sync resumes the persisted cursor. Each successful page writes CRM data, audit/outbox, progress and the next cursor in one transaction. Failed persistence does not advance the cursor. Partial work survives retries; retry budget is per page. Client cursor injection is rejected. Graph delta URLs must remain on the exact official host and inbox delta resource even when loaded from storage. Cancellation and reset require integration write permission; reset rejects active jobs.

Messages distinguish queued, sending, sent, delivered, read, failed and unknown. Delivery callbacks never downgrade a delivered/read message. Lost workers and ambiguous external writes become UNKNOWN; they are not automatically resent. Outbound HTTP 429 responses carry bounded Retry-After into durable scheduling.

Contact matching considers server-owned provider conversation relationships, then provider-verified email/phone, then an existing verified relationship. Unverified email and names alone never attach or merge contacts. Multiple candidates are AMBIGUOUS and require review. Imported provider leads retain source IDs and provenance; unverified supplied addresses do not merge records.

## Official references verified during implementation

- [Google OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Gmail synchronization](https://developers.google.com/workspace/gmail/api/guides/sync)
- [Microsoft Graph delta state tokens](https://learn.microsoft.com/en-us/graph/delta-query-overview)
- [Microsoft Graph create message](https://learn.microsoft.com/en-us/graph/api/user-post-messages?view=graph-rest-1.0)
- [Meta-owned WhatsApp webhook payload reference](https://www.postman.com/meta/whatsapp-business-platform/folder/tduohwq/webhook-payload-reference)
- [LinkedIn OIDC supported identity contract](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2)
- [Google Ads lead form webhook contract](https://developers.google.com/google-ads/webhook/docs/implementation)
- [Google Ads lead submission field schema](https://raw.githubusercontent.com/googleapis/googleapis/master/google/ads/googleads/v23/resources/lead_form_submission_data.proto)
- [Apollo authentication](https://docs.apollo.io/reference/authentication)
- [Apollo people enrichment and credit behavior](https://docs.apollo.io/reference/people-enrichment)
- [Apollo enrichment request headers and response provenance](https://docs.apollo.io/docs/enrich-people-data)

## Executed evidence

`tests/test_checkpoint56_providers.py` exercises real provider request/response shapes, unsupported operations, OAuth state/PKCE parameters, cursor SSRF rejection, rate-limit/unknown failures, tenant-local adapter configuration, actual PostgreSQL matching, sync rollback and cancellation, signed HTTP webhook ingress, provider ID deduplication, health-verified credential activation, Meta challenge validation, WhatsApp window enforcement, receipt dead letters and monotonic message delivery.

A dedicated concurrency test uses three independent restricted-role PostgreSQL connections and simultaneous HTTP requests. It asserts one accepted receipt, two duplicate acknowledgements, one durable job and one CRM message. Both required complete lead/AI and inbound/AI communication chains are exercised in `tests/test_checkpoint6_workforce.py`. CI records authoritative exact-revision counts. A local Bandit scan of the provider/API/worker implementation completed with zero findings.

## Free-first activation

SERVICE: Apollo enrichment. WHY: the official API may consume plan credits (including some data lookups). FREE ALTERNATIVE: use known user-supplied CRM data and approved public sources. LOCAL ALTERNATIVE: locally enrich from approved imported records. SUPABASE ALTERNATIVE: store approved reference datasets and perform tenant-scoped matching; Supabase does not replace Apollo data licensing. COST: provider-plan dependent; no purchase or credit-consuming live call was made.

WhatsApp and other platform actions may have provider-specific charges or require account approval. No paid campaign, live message or provider credit was activated during implementation.


Enrichment accepts exactly one server-owned `contact_id` or `lead_id` at `POST /api/v1/integrations/{id}/enrich`. A lead must have a linked contact with an email; the response stores provider ID and provenance as supplemental data on the contact and lead. It never silently merges identities. Apollo credit-consuming enrichment remains disabled by default.

OAuth callbacks revalidate current membership and the locked integration after the external exchange. Disconnect, a changed provider configuration, and a newer authorization flow invalidate the consumed session and prevent credential resurrection. Credential writes validate bounded string fields and timezone-aware ISO8601 expiry without echoing secret values in errors.
