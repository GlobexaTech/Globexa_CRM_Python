# Checkpoint 2 revised implementation

Gate 2 is evaluated against the exact branch SHA by GitHub Actions. The workflow publishes the executed checklist in its job summary and `checkpoint-2-<sha>` evidence artifact. Require a successful final workflow conclusion before accepting that SHA. Do not merge into master or begin Checkpoint 3 based on local results alone.

## Baseline and branch

- Branch: `checkpoint-2-security-hardening`.
- Implementation started at verified SHA `725acda5e4943d6c2ed9b1d7b47035a897c43c41`.
- Baseline CI: [run 33722409634](https://github.com/GlobexaTech/Globexa_CRM_Python/actions/runs/33722409634), 21 tests, migrations, mappers and Celery registration passed.
- Local baseline: compile succeeded, migration head `006_add_missing_enum_labels`, all 21 tests passed on isolated PostgreSQL 18. Docker Desktop could not start locally; PostgreSQL 16 and Redis 7 are mandatory in final CI.
- Original test files/assertions remain intact. Pre-existing untracked billing/search files are preserved and excluded from this implementation.
- Previous remote implementation `71fbc0c` and `checkpoint-2-pre-audit-backup` were inspected as references. Their security modules were not copied. A history-only merge preserves the old remote tip while retaining the revised implementation tree.

## Architecture mapping

| Phases | Implementation |
| --- | --- |
| 1–3: tenancy | Metadata-discovered ENABLE/FORCE RLS, transaction-local tenant context, identity/workspace policies, composite tenant foreign keys, restricted-role regression tests. |
| 4–5: credentials/integrations | Central CredentialService and encrypted model types cover integration access/refresh tokens, email credentials, sending-domain configuration, OAuthToken and webhook secrets. Existing Integration, WebhookEndpoint and IntegrationSyncLog retain their storage identities; Webhook/SyncJob are aliases. |
| 6: webhooks | Public `/api/v1/hooks/{endpoint_id}` verifies raw-body signatures and signed timestamps, resolves the stored tenant, and persists receipt/outbox atomically. Duplicate delivery is acknowledged without another event. The unsigned legacy receiver is removed. |
| 7: events | Versioned DomainEvent, known event names, ORM publishing, transactional outbox, Celery publisher, subscriber protocol, delivery receipts and row locks. |
| 8: AI Gateway | Generate/chat/embed contract, compatible provider transport, configured model routes and fallback. Existing AIRouter callers use the gateway. Each attempt writes an independent durable usage/audit transaction, including failures. |
| 9–11: permissions | One authoritative role map, explicit AI Agent permissions, strict user/membership inputs and protected-field validation. Approved AI tools call CRM APIs with fresh server-side permission enforcement; direct legacy assistant handler dispatch is removed. |
| 12: workers | Active workers receive tenant_id and own async database engines with NullPool. A global dispatcher enumerates only tenant IDs and fans out scoped jobs. |
| 13: automation | Workflow, Trigger, Condition, Action, ExecutionLog and permission-checked workflow configuration API. New workflows remain disabled; no autonomous runner. |
| 14: SaaS | Global Plan/Feature/PlanFeature catalog; tenant entitlements and usage; row-locked consumption. Provisioning is data-driven. Customer-facing direct package/entitlement mutation endpoints are removed to prevent self-upgrades. |
| 15: search | SearchBackend protocol and indexed PostgreSQL FTS for leads, contacts, messages, tasks, campaigns and agent definitions. API checks permissions and tenant ownership. |
| 16: audit | Mutation audit, credential rotations, login/logout, durable failed authentication, webhook failures, worker completion and AI attempts. Secret fields are redacted; runtime audit writes are append-only. |
| 17–18: production | Key/configuration validation, runtime-role validation, non-root production image, internal DB/Redis networking and CI evidence artifacts. |

The resource flow is UI/API resources → entities → permissions → transactional events → approved AI capabilities. Existing sales_manager and sales_executive roles represent Manager and Sales Agent. Tenant represents a workspace; Company represents a CRM organization. Roles and permissions are a code catalog rather than duplicate database tables.

## Database changes

Migration head: `010_auth_audit`. There are 51 tables containing tenant_id, plus RLS on shared users and tenants: **53 protected tables**. The inventory test fails if a model table is absent or unprotected. Three baseline models lacked tables; migration 009 adds products, proposal_templates and pending_leads.

Migration 007 discovers tenant tables and protects every one. It also converts existing plaintext credentials transactionally; populated credential upgrades require SECURITY_CREDENTIAL_ENCRYPTION_KEY. New plaintext SQL writes fail check constraints. Invalid cross-tenant references fail composite foreign keys. Security migrations refuse automatic downgrades that would expose data.

The full table list is generated in `RLS_TABLE_INVENTORY.md` from SQLAlchemy metadata. Users may read their own memberships across workspaces for login and tenant switching, while business-table access remains bound to one active tenant. Global plan/feature catalogs contain no customer data. Global security_events stores pre-tenant authentication outcome fingerprints and denies runtime reads, updates and deletes.

## Runtime boundaries

API and workers must use globexa_runtime (NOSUPERUSER, NOBYPASSRLS), never the migration account. Production API startup and worker database access reject privileged roles or missing ENABLE/FORCE RLS coverage. Disabled identities are rejected during tenant resolution, including routes that do not load a user dependency. Run scripts/provision_runtime.py after migrations. Bootstrap lookup functions use SECURITY DEFINER with fixed search paths, schema-qualified objects and revoked PUBLIC execution. Their owner must be a trusted migration administrator with superuser/BYPASSRLS; it is never the API/worker identity.

RLS protects against omitted application filters and cross-tenant references. The application remains the trusted database client responsible for JWT validation and membership verification before assigning transaction context. Runtime database credentials must remain private.

Meta-family HMAC covers the raw body and requires signed entry timestamps within five minutes. Generic webhooks sign timestamp, a period, and raw_body. Stripe signature envelopes are supported, but no billing consumer is enabled. Unknown signature schemes fail closed. Queue messages contain tenant/event IDs rather than provider secrets.

## Evidence

Local execution reached **63 passing tests**: the original 21 plus 42 security/runtime checks. These cover restricted-role SQL, physical connection reuse, real Celery eager execution, webhook deduplication, entitlement limits, FTS, OAuth ciphertext, workflow configuration, AI fallback, independent failure ledgers, disabled identities, privilege escalation and production database guards. No paid model calls, outbound campaigns or live provider credentials are used.

The first revised candidate, `8b2ed8ca182be534e286c538c0e734d98570e791`, passed [CI run 34255985859](https://github.com/GlobexaTech/Globexa_CRM_Python/actions/runs/34255985859): all 56 then-existing tests, PostgreSQL 16, Redis 7, migrations, all four scans and the production container. Seven additional authorization/runtime regressions and the guards above were subsequently added. Their final-SHA CI evidence is generated by the workflow rather than asserting that an earlier run covered later changes.

Local Ruff correctness scan (E9,F63,F7,F82) passes. Bandit reports no findings in tracked application code. Two false-positive suppressions document the container bind address and OAuth token-type literal. Pip-audit reports no known vulnerabilities after replacing python-jose with PyJWT and updating build tools. Untracked local billing/search files are outside the release.

Final acceptance comes from `.github/workflows/checkpoint-2.yml` on the final SHA. Artifact `checkpoint-2-<sha>` records commit/run IDs, migration head, pytest JUnit/text, Ruff, Bandit, pip-audit, Gitleaks and resolved dependency versions. After all execution checks succeed, CI generates `DEMO_GATE_2_CHECKLIST.md` inside that artifact with the actual SHA, run ID and test count. CI additionally verifies PostgreSQL 16, Redis 7, Celery registration, the image build, non-root UID and absence of development dependencies.

## Setup

1. Generate independent JWT and Fernet keys. Set SECURITY_SECRET_KEY, SECURITY_CREDENTIAL_ENCRYPTION_KEY, MIGRATION_DATABASE_PASSWORD, RUNTIME_DATABASE_PASSWORD and REDIS_PASSWORD outside Git. Generate URL-safe hexadecimal database/Redis passwords.
2. Start postgres and redis with `docker compose -f docker-compose.production.yml up -d postgres redis`.
3. Run `alembic upgrade head` using the migration identity and encryption key. For a one-shot Compose API container, override APP_ENVIRONMENT=migration, DATABASE_USERNAME=crm_migrator and DATABASE_PASSWORD to the migration password, then invoke Alembic.
4. Run `python scripts/provision_runtime.py` using the migration connection and RUNTIME_DATABASE_PASSWORD. Re-run after schema changes. Never expose this command through a customer API.
5. Start api, worker and beat with the production Compose file. API binds to loopback; configure HTTPS termination and actual CORS origins. Configure provider endpoints/models and secrets in the deployment environment.
6. Provision Plan/Feature/PlanFeature administratively, then call EntitlementService.provision for each tenant. No prices or entitlements are invented. Webhook creation accepts a provider signing secret and returns only endpoint ID/ingress path.

Development checks require a disposable PostgreSQL database and Redis 7. Install `pip install -e '.[test]' ruff bandit pip-audit`, run migrations and provision the runtime role, then `pytest -q`. RUNTIME_DATABASE_PASSWORD must match the role used by pool/worker tests. Do not run these tests on a production database.

## Deliberate limitations

- The user authorized deriving the foundation from the revised brief and repository. Frontend integration/visual verification is separate.
- Full event consumers, autonomous agents, visual workflow execution, billing lifecycle processing and live-provider certification are outside this foundation. Workflows remain inactive.
- Embedding requires a compatible provider/model endpoint. Unconfigured model rates produce unknown/null cost, never invented prices.
- Meta-family payloads without supported signed entry timestamps are rejected; additional payload contracts need dedicated adapters/tests.
- Legacy placeholder business jobs/providers are not claimed as complete business workflows. No external email, campaign, prospect crawl or paid AI call was executed.
- Local PostgreSQL was version 18. Gate 2 requires final PostgreSQL 16/Redis 7 CI and container evidence. No production deployment is claimed.

Design references: [PostgreSQL row security](https://www.postgresql.org/docs/16/ddl-rowsecurity.html), [Stripe webhook signatures](https://docs.stripe.com/webhooks).
