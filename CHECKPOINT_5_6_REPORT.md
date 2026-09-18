# Checkpoint 5 + 6: provider operations, AI workforce and security

Branch: `checkpoint-5-6-integrations-ai-workforce` in `GlobexaTech/Globexa_CRM_Python`.

The implementation combines the accepted Checkpoint 4 application, the remote RLS changes, and the local provider work. The supplied [implementation brief](docs/checkpoint5_6/IMPLEMENTATION_BRIEF.md) remains the requirement source. Original local work was preserved; the completed implementation lives in the GlobexaTech checkout.

## Release evidence

The authoritative release result is `CHECKPOINT_5_6_GATE.txt` inside the GitHub Actions artifact `checkpoint-5-6-<full SHA>`. The [Checkpoint 5 + 6 workflow](.github/workflows/checkpoint-5-6.yml) verifies its own checked-out SHA. A green run for an earlier commit does not approve later changes. See [gate rules and history-scan triage](docs/checkpoint56/RELEASE_GATE.md).

The gate executes all backend tests, restricted-role PostgreSQL isolation checks, provider HTTP contracts, AI/approval integration tests, frontend unit tests, browser workflows, four viewport accessibility checks, schema generation, migrations, Docker image checks, Bandit, pip-audit, npm audit, and current-source/full-history Gitleaks scans. Mandatory failures, errors and skipped tests prevent the pass marker. Local evidence is kept in ignored `evidence/`; private settings, credentials and server logs are excluded from published artifacts.

## Classification

| Classification | Meaning for this checkpoint |
| --- | --- |
| IMPLEMENTED | Persisted CRM/provider/workforce services, API authorization, real Celery scheduling, approval enforcement, UI and security controls exist and are exercised by executable tests. |
| PROVIDER-READY | The documented supported capabilities use actual official request/response contracts and deterministic external transport tests. Configuration, app permissions, quotas and account approval remain operator prerequisites. |
| LIVE-CERTIFIED | **BLOCKED — CREDENTIAL REQUIRED.** No live Google, Microsoft, Meta, LinkedIn, Google Ads, Apollo or model-provider account was used. No paid resource, provider credit, advertisement or real outbound message was activated. |

Unsupported provider capabilities are explicit. In particular, LinkedIn exposes OIDC account connection/health only; partner-only exports, messaging and refresh are unavailable. Instagram does not claim arbitrary outbound messaging. WhatsApp supports text within its verified conversation window, with no media upload or template submission. Apollo enrichment remains disabled by default because it can consume credits. Google Ads' official shared-key webhook has no signed timestamp: permanent provider lead-ID deduplication is used and documented rather than inventing a signature. [Provider contracts, callback details, official sources and limitations](docs/checkpoint56/PROVIDER_CONTRACTS.md).

## Database and tenant security

The previously divergent migration heads merge at `013_merge_rls_heads`. New frozen schema DDL introduces `agent_executions`, `agent_memory`, `approval_requests`, `sync_jobs`, `sync_cursors` and `dead_letter_events`, plus receipt lifecycle fields and nullable measured usage. Subsequent migrations persist execution attribution and update the narrow webhook identity lookup. Alembic remains the schema authority; test runs never substitute `create_all()`.

Every tenant-owned table is covered by FORCE RLS. Mandatory restrictive tenant equality complements existing permissive policies; a metadata flag such as `app.is_admin=true` cannot bypass it. Identity discovery retains its separate membership-based policies. The runtime role has neither SUPERUSER nor BYPASSRLS, cannot modify migration/global plan tables, and cannot update/delete immutable audit records. Compound tenant foreign keys prevent cross-tenant parent references.

`tests/test_rls.py` creates fixture identities with the migration administrator, then performs assertions only through the restricted runtime connection. It tests positive and negative SELECT/INSERT/UPDATE/DELETE in both directions, no-context denial, all-table policy coverage, compound foreign keys, one physical connection reused across tenants, rollback, exceptions, statement timeout, and concurrent tasks. The original remote RLS tests were repaired because their administrator fixture could not prove runtime isolation.

The remote middleware regression that removed verified identity context before tenant lookup is fixed. Membership permissions are refreshed from the database even when the ORM session previously loaded the same membership. API and worker authorization recheck current membership instead of trusting JWT role claims or browser controls.

## Authentication and deployment

Access and refresh tokens include signed token/session identifiers and a bounded family lifetime. Redis atomically consumes refresh identifiers. Replaying a consumed refresh revokes that session family; logout revokes both access and refresh tokens for the family. Other logins remain independent. Disabled users/tenants and removed memberships lose access. An unavailable revocation store fails authentication closed. Purpose-limited unsubscribe links have a separate decoder and cannot authenticate.

Existing tokens without the new session claims require a fresh login. Production Redis must preserve revocation state. The production Compose definition uses a private network, authenticated Redis, a persistent volume, AOF with `appendfsync always`, and no eviction. If its keyspace is lost, rotate the JWT signing key and require new logins before restoring service; do not restart with an empty revocation store and assume previous revocations remain effective.

Production rejects debug/SQL echo, missing encryption, default or weak credentials, unsafe CORS, public Redis endpoints, unauthenticated broker/result connections and non-JSON task serialization. Database and Redis URL credentials are encoded. API docs remain disabled outside debug mode. The production image runs without root, test tooling or external test adapters. Provisioning and migrations use a separate administrator role. Complete environment placeholders are in [.env.example](.env.example).

## Provider execution

OAuth state is hashed, single-use and bound to actor/tenant/integration/redirect; the PKCE verifier and provider tokens are encrypted. Provider health is tested before activation. Delayed token exchanges revalidate authorization and integration state. Disconnect/configuration changes cannot be undone by a stale callback. Stable browser callback: `/integrations/callback`; configure the exact URI `https://<frontend-origin>/integrations/callback` in the provider application and the corresponding `CRM_<PROVIDER>_REDIRECT_URI`.

Signed webhook ingress enforces bounded bytes, the provider's real authentication contract, signed timestamp where supplied, replay/idempotency rules and endpoint rate limits before durable normalization. Ingress emits `webhook.received`; only a persisted message/lead mutation emits its domain event. Concurrent receipts are serialized; differing JSON representations still deduplicate using provider IDs. Completed/dead-letter receipt payloads are cleared and failures retain safe error codes.

Sync pages persist normalized records, progress and the next server-owned cursor atomically. Browser-supplied cursors are rejected. Initial/incremental pagination, partial work, retry, cancellation and reset are explicit. Provider-ID or verified-address matching never merges names or unverified addresses. Ambiguous matches require review.

Messages distinguish queued, sending, sent, delivered, read, failed and unknown. A timeout after an external write or a lost worker never silently triggers another send. Delivery callbacks cannot downgrade delivered/read states. Retries are bounded and respect provider retry metadata. Legacy raw integration/email/AI task names fail closed in favor of persisted operation IDs.

## AI and approval execution

Research, Lead Mining, Sales, CRM Analyst, Support and Supervisor use durable execution rows, the shared model gateway, current RBAC, tenant-owned records, an explicit tool allowlist, and bounded model/tool budgets. Supervisor creates real child executions, monitors terminal outcomes, retries only eligible safe failures, and summarizes their stored results. Optional event triggers are disabled until `WORKFORCE_EVENT_TRIGGERS=true`; they never grant additional permissions.

All sixteen required tools have strict schemas and server-owned identity. Model-produced writes and sends become proposals. A different authorized human must approve the exact action hash, including target, recipient, content, provider/account binding and attachments. The worker checks current authority and the binding again; queued sends retain that binding until the actual external call. Changes require a new approval. Unknown sends cannot be automatically retried.

Untrusted CRM/provider/web content is treated as data; selected adversarial instructions are rejected, and model output cannot expand server-enforced permissions, tool scope, tenant identity or approvals. Research accepts only user-selected HTTPS URLs on administrator-approved hosts; DNS results must be public and the verified address is pinned to the TLS connection. Every redirect is checked again. Credentials, arbitrary headers, private/metadata addresses, oversized bodies and unsupported content types are rejected.

Working memory stores bounded execution metadata. Retained memory needs independent approval, an expiry and explicit deletion support; scheduler cleanup removes expired entries. Customer content is not automatically copied into long-term memory. Usage links to the execution and records actual provider measurements, latency, model, status and tools. Missing token/cost measurements remain unknown. [Detailed AI architecture, limits and activation](docs/checkpoint56/AI_WORKFORCE.md).

## Product integration

The Integration Hub exposes capability/configuration/health states, credential activation, sync progress, cancellation, receipt history and callback handling. Conversations expose provider delivery states and WhatsApp recipient validation. `/ai-workforce`, `/supervisor` and `/approvals` expose real execution/child/approval records and retained-memory controls. Customer 360 links the related executions, conversations and approved outcomes. All use the typed BFF, same-origin protection, tenant-scoped cache and generated API contract.

The two required complete flows are executed against PostgreSQL with external HTTP transport doubles:

1. Lead → Research → measured AI score → Sales recommendation → draft → independent approval → send → conversation → Customer 360.
2. Signed inbound webhook → persisted conversation → Support analysis → draft → independent approval → send → provider delivery state.

A browser flow additionally creates the proposals in the UI, approves with another human account, waits for actual Celery execution, and verifies the provider ID in the conversation and Customer 360. No in-memory database, eager Celery replacement or authentication bypass is installed in the browser runtime.

## Secrets and remaining operational prerequisites

Current publishable source is scanned without leaking matched values. Full history retains 22 reviewed findings: 17 documentation placeholders and five synthetic test-key occurrences. They are recorded with immutable fingerprints and classifications; raw redacted evidence remains available. Unknown, moved, duplicated, unredacted or altered findings fail the gate. No broad path or rule suppression is added. Historical test literals are not production credentials, but **ROTATION REQUIRED** applies to any deployment that reused an old static test key outside the isolated tests. Current CI/runtime keys are generated independently.

Live certification still requires provider credentials, approved scopes, configured callback URLs and account ownership checks. No provider-ready result guarantees approval or delivery from a live external platform. File/media uploads and unsupported provider operations are not presented as implemented. Production backup/restore, HTTPS ingress, DNS/private network configuration and live-provider smoke tests remain deployment responsibilities.

See [phase-by-phase traceability](CHECKPOINT_5_6_TRACEABILITY.md) for implementation and test locations.
