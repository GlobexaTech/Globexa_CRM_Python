# Checkpoint 5 + 6 requirement traceability

Requirement source: [supplied brief](docs/checkpoint5_6/IMPLEMENTATION_BRIEF.md). Verification is executable; final counts and the exact commit are in the SHA-specific CI gate artifact. External provider certification remains credential-blocked independently of software verification.

| Phase | Implementation | Executed verification |
| --- | --- | --- |
| 1–2 Repository and audit | Required branch; preserved original checkout; reviewed and integrated RLS/provider/AI changes | Git ancestry in workflow; final `git status`, local/remote SHA comparison |
| 3 PostgreSQL/Alembic | Migrations 013–017 merge both existing heads and add frozen provider/workforce schema | Fresh local isolated database, `alembic upgrade head`, `alembic current`, fresh PostgreSQL 16 in CI |
| 4 RLS | `tenant_context.py`, `runtime_security.py`, restrictive policies, tenant compound FKs | `test_rls.py`; original `test_checkpoint2_runtime.py`; independent provider concurrency sessions |
| 5 Auth/RBAC | `security.py`, `token_sessions.py`, tenant middleware, live membership refresh, BFF session/origin checks | `test_auth.py`, `test_checkpoint56_auth.py`, auth/role/tenant browser tests |
| 6 Secrets | Credential encryption, `.env.example`, ignored private evidence, exact history triage | Current-source Gitleaks; full-history raw redacted scan + strict reviewed-fingerprint triage |
| 7 Scanners | Mandatory release workflow | Bandit, pip-audit, npm audit, Gitleaks source/history; no high/critical bypass |
| 8 Capability architecture | `crm/providers.py`, integration status/catalog/API and UI | `test_checkpoint56_providers.py`, Integration Hub browser tests |
| 9 Gmail | OAuth/PKCE/state, refresh/revoke/profile, history/full sync, MIME send IDs | HTTP contract/refresh/cursor/health tests; stable callback browser flow |
| 10 Outlook | Graph OAuth, refresh/profile, delta/next-link sync, immutable draft ID then send | Official-shape draft/send and delta URL tests; provider-error/unknown tests |
| 11 WhatsApp | Cloud API text, verified 24-hour recipient window, HMAC/statuses/Meta challenge | Actual signed ingress/receipt worker; failed/delivered/read and concurrent dedupe tests |
| 12 Meta/Instagram | OAuth where supported, tenant account mapping, signed ingress, form sync and source IDs | Meta form pagination + Instagram normalization; capability rejection tests |
| 13 LinkedIn | Official OIDC/userinfo contract; restricted operations unavailable | Explicit unsupported-operation/identity-verification tests |
| 14 Google Ads | OAuth/read GAQL + lead sync; official shared-key lead callback | Field shape/pagination/shared-key/event-ID contract tests; no paid campaign actions |
| 15 Apollo | API-key health/enrichment/provenance; explicit credit-consumption opt-in | Health/enrich/not-found/rate/disabled-by-default tests |
| 16 Webhook pipeline | `hooks.py`, `webhooks.py`, `provider_pipeline.py`, durable receipts/OperationJob | Signed HTTP ingress, concurrent requests, differently encoded duplicates, atomic normalization/dead letter |
| 17 Sync | Server cursor, durable SyncJob/SyncCursor, atomic page writes, cancel/reset | Persistence failure leaves cursor unchanged; pagination/retry/cancel tests |
| 18 Message lifecycle | `conversations.py`, provider writes, job fencing and delivery normalization | Sent/provider ID; delivered/read monotonicity; unknown does not resend |
| 19 Identity matching | Provider relationship → verified email/phone → verified relationship; ambiguous review | Positive/ambiguous/unverified-address and names-only rejection tests |
| 20 Six agents | `ai/agent.py`, `supervisor.py`, gateway, workforce API | All agents + Supervisor child execution against actual DB and model HTTP doubles |
| 21 Sixteen tools | `workforce_tools.py`, strict argument schemas, fresh permission/ownership checks | All read/mutation tool tests, authority injection/foreign IDs/idempotency tests |
| 22 Prompt injection | `safety.py`, untrusted envelopes, tool allowlist/approval boundary | Adversarial instruction/identity/exfiltration strings rejected before action |
| 23 Memory | `memory.py`, approved retained records, bounded TTL/delete/scheduled expiry | Independent approval, expiry/purge and deletion tests; browser memory flow |
| 24 Agent lifecycle | AgentExecution + OperationJob, real Celery executor | Queued/running/terminal persistence, concurrent idempotency, in-flight cancellation, safe retry |
| 25 Usage | Nullable measured usage/execution FK, gateway and analytics | Known/unknown usage, actual separate ledger connection, DTO and analytics checks |
| 26 Approval | `approval.py`, exact hash/provider binding, downstream send binding | Self-approval/tamper/expiry/changed-target/revoked-authority/idempotency tests |
| 27 Supervisor | Bounded decomposition/children/polling/retry/summary | Persisted child results, bounded failed-child retry/recovery/exhaustion and consolidation; actual worker browser flow |
| 28 Event-driven work | Outbox subscribers, opt-in workforce events, deterministic event key | Lead/message/deal/campaign trigger contracts and replay idempotency |
| 29 Frontend | Integration Hub/Conversations/Workforce/Supervisor/Approvals/Customer 360 | Unit tests; actual backend/worker browser E2E; axe + 1440/1280/768/390 layouts |
| 30 Upload/SSRF | No file/media upload capability advertised; `research.py` public-HTTPS DNS pinning | Private/metadata DNS, URL/redirect rejection, pinned-address handoff transport test, MIME/byte bounds; no live DNS-rebinding/TLS certification |
| 31 API security | Global bounded body middleware, parameterized search, safe error responses, CSRF/rate protections | Body/chunked size, SQL injection, original security suite, XSS/CSRF browser checks |
| 32 Redis/Celery | Private authenticated Redis, explicit tenant task IDs, durable jobs, no raw-send task bypass | Redis 7 rate/refresh atomicity; restricted worker sessions; real scheduled browser execution |
| 33 Production guards | `config.py`, Compose non-root/private network/AOF/noeviction, disabled docs | Positive + negative configuration tests, Docker runtime exclusion checks |
| 34 Tests | Full pytest/frontend unit/browser collection with no skip allowance | SHA-specific JUnit/TAP reports and scanner reports in sanitized CI artifact |
| 35 Both complete flows | `test_checkpoint6_workforce.py`, `workforce.spec.ts` | Lead/research/score/sales/approval/send/C360 and signed inbound/analysis/approval/send/provider state |
| 36 CI | `.github/workflows/checkpoint-5-6.yml`, `checkpoint56_gate.py` | Fail-closed gate unit tests; complete remote run at exact final pushed SHA |
| 37 Documentation | This file, report, provider contracts, AI architecture, gate notes, environment examples | Contract generation and source review; limitations explicitly classified |

Important test changes are intentional contract corrections: the inbound email fixture now explicitly marks its verified identity; Outlook uses real draft-creation and send-response shapes; ingress is a webhook event until CRM normalization; runtime RLS tests no longer run assertions as an administrator. Tests were not removed to conceal failures.
