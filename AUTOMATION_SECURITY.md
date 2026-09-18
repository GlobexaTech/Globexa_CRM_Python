# Automation security and operating controls

## Trust boundaries

- All twelve new tables use PostgreSQL FORCE RLS and tenant guards. Compound tenant foreign keys prevent cross-tenant references. Runtime startup rejects superuser/BYPASSRLS roles and incomplete tenant migrations.
- API authorization, live worker authorization, entity ownership and provider authority are separate checks. Revoked workflow-owner permissions terminate queued execution. API identities come from the existing authenticated session, never workflow input.
- Published versions are immutable, hashed and bound to each execution. Human approvals bind execution, version, step, normalized action payload and provider credential grant. A different authorized human must approve. AI-agent roles and self-approval are rejected. Changes, cancellation, expiry and revoked permissions invalidate execution authority.
- External sends always require approval. Actions populated from earlier step output require approval as well. Administrators can additionally require approval for internal actions; workflow input and model output cannot turn this off.
- Webhooks require an administrator-configured exact HTTPS host, public DNS resolution, a pinned TLS connection and port 443. Credentials, query strings, fragments and redirects are rejected. The request body is bounded and cannot contain credentials or identity overrides. Timeout and ambiguous server failures are unknown, not successful or automatically retryable.
- AI receives a minimized, bounded untrusted-data envelope and a strict output schema. It cannot select identity, permissions, SQL, shell commands or arbitrary tools. Prompt-injection filtering complements, rather than replaces, server-side authorization and approvals.
- Atomic execution idempotency prevents duplicate internal effects. Durable external claims prevent blind replay. Cancellation cannot unsend a request already accepted by a remote provider; its actual outcome is retained.

## Configuration

Existing server-only `CRM_AI_PROVIDER`, `CRM_AI_MODEL`, `CRM_AI_BASE_URL` and, when needed, `CRM_AI_API_KEY` select the approved primary route. Optional `CRM_AI_FALLBACK_PROVIDER`, `CRM_AI_FALLBACK_MODEL`, `CRM_AI_FALLBACK_BASE_URL` and `CRM_AI_FALLBACK_API_KEY` must explicitly identify a distinct supported provider. Local Ollama requires no billing account. No live provider calls are needed for the automated contract tests.

`AUTOMATION_WEBHOOK_ALLOWED_HOSTS` is a comma-separated exact host allowlist. It defaults to empty, which disables webhook destinations. Do not place API keys, bearer tokens or customer secrets in workflow variables or URLs. Integration IDs are references; encrypted provider credentials remain in the existing integration store.

Tenant administrators configure `/automation/policy`. Defaults allow 1,000 daily/10,000 monthly executions, 100 pending executions, 64 steps, chain depth 5, runtime seven days, five AI calls per execution, 20 daily/200 monthly AI calls, and 120 tenant/60 action/20 provider step admissions per minute. Zero AI limits disable AI usage. Provider usage with missing token/cost measurements remains unknown.

## Deployment and incident procedure

1. Verify the exact intended Git SHA's Checkpoint 7 CI artifact; do not substitute an older checkpoint's gate.
2. Back up the database and rehearse restoration. Apply migration 018 using the migration administrator, then run `scripts/provision_runtime.py` with a restricted runtime role. Never use the migration administrator as the API or worker account.
3. Configure production origins, secure session cookies, Redis credentials, worker processes, scheduler, approved AI/provider credentials and least-privilege grants using the existing runbooks. Production deployment is a separate operational action.
4. Start with conservative limits and test tenant-specific workflows. Publish only reviewed versions. Confirm independent reviewers can inspect exact payloads and reject requests.
5. Monitor failed/unknown executions, dead letters, queue age, integration health and measured/unknown AI usage. Pause or disable workflows before investigating a provider incident.
6. Reconcile uncertain sends with provider records. Do not retry an unknown outcome merely because an HTTP response is missing. Only retry known-safe bounded failures.
7. Roll back application traffic only to a compatible revision. Preserve execution and approval evidence. Never edit an already-published definition to change a running workflow.

Live email/WhatsApp/AI certification requires real credentials and permitted test recipients. Automated tests use deterministic external transport adapters with real CRM services and persistence; they do not certify external accounts or production infrastructure.
