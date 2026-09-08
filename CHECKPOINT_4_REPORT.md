# Checkpoint 4 — frontend product integration

## Executive Summary

The approved Globexa UI Lab frontend now lives in `frontend/` of `GlobexaTech/Globexa_CRM_Python`, on `checkpoint-4-frontend-integration`. The application retains the Globexa blue/white surfaces, grouped sidebar, command-center hero, CRM tables, lead drawer and deal board. CRM records and operational outcomes come from the authenticated backend.

## Source and revision boundary

- Approved backend base: `0d030cf4d0f0f00cec05f443d91c41f44ee7ba43`, Checkpoint 3, verified by Actions run `34267879955`.
- Approved UI archive: `globexa_crm_ui_lab.zip`, SHA-256 `04661ff9dad2b44f4bdc7e00833e18af1f2bdcafd16f06f0dc3e1b2349a8cbc8`; its Git metadata had no remote. Source imported in `ee4bf6f`.
- Only the archive's 42 source/configuration/asset files were imported. Bundled dependencies, caches and nested Git history were excluded.
- Source precedence and requirements are preserved in [the brief](docs/checkpoint4/IMPLEMENTATION_BRIEF.md), [the original audit](docs/checkpoint4/UI_LAB_AUDIT.md) and [the inspected backend baseline](docs/checkpoint4/BACKEND_BASELINE.md).
- The final tested revision is the full SHA in the CI artifact `CHECKPOINT_4_GATE.txt`. A previous revision's green run does not approve this revision. The workflow records its own `git rev-parse HEAD`.
- The original backend checkout's unrelated untracked billing/search work is excluded. The master branch is not changed.

## Frontend Architecture

| Layer | Implementation |
| --- | --- |
| UI | Next.js 16 App Router, React 19, retained Tailwind/Globexa theme |
| Shared transport | `src/api/client.ts`: typed methods, bounded timeout/cancellation, structured errors, workspace version and idempotency headers |
| Contract | `frontend/openapi.json`, generated `src/api/generated.ts`; CI regenerates and rejects drift |
| Domain services | **3** service modules: `crm.ts`, `operations.ts`, `workspace.ts` |
| State | TanStack Query; keys contain tenant ID, workspace version and resource URL; no CRM browser persistence |
| Authentication | Same-origin Next route handlers; opaque HttpOnly cookie; encrypted server sessions in Redis |
| Server session storage | AES-256-GCM, distinct random nonce per write, bounded lifetime, Redis locks, conditional refresh saves and deletion on logout |
| Authorization | Live backend membership permissions; backend remains authoritative for every mutation |
| Async work | Actual OperationJob IDs, terminal state polling, explicit failed/unknown outcomes and allowed retries |
| UI feedback | Shared loading/error states, native top-layer dialogs, destructive confirmations and cache reconciliation |

## Authentication

No access token, refresh token or provider credential is stored in localStorage, sessionStorage or client-readable cookies. Production cookies use the `__Host-` prefix, HttpOnly, Secure and SameSite=Lax. Login, session restoration, access-token refresh, invalid refresh and logout are tested through the real backend. Unsafe requests require the exact configured Origin. The proxy uses a fixed backend origin and a route allowlist; the only allowed authentication namespace route is the current user's profile. Tenant IDs supplied by the browser cannot replace the token's tenant.

## Tenant Architecture

Switching tenants clears queries, cancels requests and replaces the workspace version. The server serializes session transitions and rejects old versions. An in-flight refresh cannot resurrect a logged-out session. Other tabs receive session-change messages; data-change broadcasts carry only a tenant invalidation hint. Focus refresh and job completion reconcile persisted records.

## RBAC

Owner, admin, sales manager, sales executive, marketing, viewer and AI-agent memberships use the backend's live permission map. Controls and navigation follow those permissions; the backend independently authorizes requests. Browser tests exercise all seven roles and a role revoked while a page is open.

## API Client

The shared client supports GET/POST/PUT/PATCH/DELETE, typed responses, cancellation, a bounded timeout, structured validation errors, Retry-After and idempotency keys. Server route handlers forward a fixed allowlist of paths and headers. Concurrent refresh is serialized in Redis; writes with uncertain outcomes are not automatically replayed. OpenAPI-generated DTOs are regenerated and compared in CI.

## CRM Integration

**15 connected modules**: dashboard, leads, contacts, companies, pipeline/deals, tasks/activities, Customer 360, conversations, campaigns, automation, integrations, controlled AI, analytics, search and settings/admin. Authentication and workspace management are shared foundations; Help is additional product guidance.

| Module | Persisted behavior |
| --- | --- |
| Dashboard | Server aggregates, real pipeline values, upcoming tasks, activity and AI insights; restricted roles see permitted navigation |
| Leads | CRUD, supported filters, UUID relations, owner assignment, detail drawer, status changes, real score jobs, linked tasks/conversations |
| Contacts | CRUD, company relation, consent/opt-out controls, customer links and confirmed deletion |
| Companies | CRUD, related contacts/leads/deals through Customer 360 |
| Pipeline/deals | Distinct deal entities, pipeline/stage management, atomic reorder, persisted mouse/keyboard moves and rollback/reconciliation on rejection |
| Tasks/activities | Backend task statuses, priorities, ownership/relations, due dates and persisted activity records |
| Customer 360 | Backend aggregate, permitted sections, restricted-section explanation, paginated timeline, notes, tasks and activities |
| Conversations | Channels, participants, real messages/unread state, queued sends and terminal job outcomes; mobile list/detail navigation |
| Campaigns | Real audience, templates, sequence steps, UTC scheduling, launch/pause/resume/cancel, recipients, suppression and unknown-delivery visibility |
| Automation | Structured approved triggers/conditions/actions, saved versions, enablement, execution logs and backend-approved retry |
| Integrations | Capability/configuration distinction, OAuth start/callback, refresh, sync jobs/history and disconnect; unsupported providers have no fake connection |
| Controlled AI | Lead score/summary, next best action, reply analysis, campaign draft and proposal draft; real gateway jobs, validated output, provenance and usage |
| Analytics | Six backend views, UTC date filters, currency-separated pipeline values, explicit unpriced AI usage and response-time sample boundaries |
| Search | Ten permission-filtered entity types, pagination, snippets and deep links to records/related conversations |
| Settings/admin | Profile, workspace metadata, authorized team creation/role/removal, read-only plan/entitlements and audit log |

Campaign lifecycle endpoints return their actual HTTP 200 persisted state. HTTP 202 operation responses mean queued work, never delivered work. `unknown` delivery is labeled **Delivery status pending verification** and has no resend button. An AI draft remains a suggestion until the user authorizes a supported action. There is no autonomous sales/research/supervisor workforce, payment lifecycle or unrestricted outreach execution.

## Customer 360

The customer route combines actual related companies, contacts, leads, deals, notes, tasks, activities and conversations. Restricted sections remain clearly identified. Creating notes, activities and tasks is checked against persisted backend records and the reloaded timeline.

## Conversations

Conversation list/detail navigation, participants and messages use real records. Sending creates a durable operation; polling distinguishes completed, failed and unknown delivery. Unknown delivery has no resend control. The browser suite verifies all three outcomes through the Celery worker.

## Campaigns

Audience, template, sequence, UTC schedule, lifecycle, recipients and statistics use backend contracts. Lifecycle responses use their actual HTTP 200 state. Worker execution, suppression and signed unsubscribe are tested. Human confirmation is required before launch and destructive lifecycle actions.

## Automation

The structured editor supports the backend's approved trigger, condition and action definitions. Enablement, revisions and execution history are persisted. A real event produces a worker execution and task; failed execution retry follows the original job and respects the backend's bounded retry policy.

## Integrations

Provider capability, deployment configuration and connected-account state are distinct. Gmail and Outlook support the implemented OAuth/provider operations; the other catalog entries expose their actual unsupported state. Browser tests cover callback completion/error, health, refresh, sync/history and disconnect. Callback parameters are removed from the browser URL.

## Controlled AI

Six supported capabilities run through durable jobs and the real gateway: lead score, lead summary, next best action, reply analysis, campaign draft and proposal draft. Responses preserve provenance and usage. Hook suggestions require review and explicit approval, after which the child AI request remains trackable. Tests substitute only the external model transport; no browser-generated AI result is accepted.

## Analytics

The six server aggregate views retain date filters, currency units and explicit unknown/unpriced values. Browser tests compare displayed metrics with the actual API response and validate reversed date ranges.

## Global Search

Search supports the ten backend entity types, permission-filtered results, bounded pagination and record deep links. Related IDs route messages and customer records correctly without inventing record URLs.

## Accessibility

Native modal dialogs provide top-layer placement, labelled controls, Escape dismissal, focus containment and restoration. Lead drawer tests wait for actual loaded controls. Axe checks run against loaded CRM route headings and responses, rather than the session-loading screen. Full finding-by-finding evidence is maintained in the frontend audit.

## Responsive Design

The desktop sidebar becomes a mobile navigation dialog. Tables and the board retain intentional horizontal scrolling inside their containers; forms and page controls must remain within the viewport. The browser suite audits 1440×900, 1280×800, 768×1024 and 390×844, plus mobile/desktop drawer interactions and reduced motion.

## Security

The backend's restricted database role and FORCE RLS remain active. Sessions are server-held and encrypted; credentials are excluded from client storage and public evidence. Same-origin checks, workspace versioning, least-privilege permissions, no uncertain write replay and non-autonomous AI boundaries are covered by executable tests. CI also runs dependency, static security and source-secret scans and inspects the production image's non-root user.

The API generator's Redocly dependency pins a vulnerable YAML parser. A scoped npm override uses the patched `js-yaml` 4.3.2 for [GHSA-2883-xcg3-v3hh](https://github.com/advisories/GHSA-2883-xcg3-v3hh); the lockfile reuses that patched version already required by ESLint. Contract generation remains unchanged, and CI continues to reject any dependency vulnerability at low severity or above.

## Backend Changes

Existing migrations and all 116 original backend tests are preserved. No database migration was added. The following changes repair required UI contracts:

1. `GET /auth/permissions` exposes the active membership's authoritative grants.
2. Pipeline/stage mutation routes use `deals:pipeline_manage`; stage creation no longer duplicates `pipeline_id` constructor arguments and validates URL/body consistency.
3. `PUT /deals/pipelines/{id}/stages/order` validates the complete tenant stage set and updates order atomically while locking the pipeline/stages.
4. Pipeline/deal/linked lead/contact responses load or serialize the declared response fields explicitly, avoiding async lazy-loading failures after a successful write.
5. Workflow execution responses include the tenant-scoped operation `job_id`, permitting the existing safe-retry endpoint to be used.
6. AI hook jobs expose only safe suggestion target fields for review, without exposing the raw operation payload.
7. Integration sync history paginates its SQL query before execution.
8. Search results include safe related-record IDs for navigation.
9. Campaign statistics include an `unknown` operation count; ambiguous delivery does not complete the campaign.
10. Team-member insertion temporarily binds a new server-generated identity for INSERT RETURNING after authorization/quota checks, then immediately restores the actor before membership creation. Membership/note responses explicitly load their declared user/author graph.
11. Response validation failures return a generic error and log field locations/types, preventing framework tracebacks containing model inputs.
12. Plan entitlement metadata uses the mapped ORM attribute during validation and the public `metadata` field during serialization, avoiding collision with SQLAlchemy's class metadata.

These changes are covered by `tests/test_checkpoint4.py` and the browser suite. The backend runtime remains a restricted PostgreSQL role with FORCE RLS. Test adapters are installed only by the isolated test bootstrap scripts and are absent from the production image.

## Testing

Run the commands in [frontend setup](frontend/README.md). Auth/client unit tests and browser journeys cover the real API, database, Redis and worker chain. Fixtures use isolated tenants and generated credentials. Only external provider transports are substituted. Test counts and outcomes are recorded in the exact-revision public CI artifact, including backend JUnit, browser JUnit and frontend unit output.

Local verification on 2026-09-09: **135 backend tests**, **30 frontend unit tests**, clean ESLint/TypeScript, production build, Ruff, Bandit, Python/npm dependency audits and Gitleaks. The full browser run passed **56 of 57** tests; its only failure was an offline-recovery test expecting automatic reconnection instead of the product's explicit **Try again** action. The corrected assertion passed its targeted rerun without changing production code. This local evidence does not replace the required single complete exact-SHA CI run. All seven accessibility cases passed, covering 64 loaded route/viewport combinations and both drawer interaction suites.

## CI

The authoritative workflow is [.github/workflows/checkpoint-4.yml](.github/workflows/checkpoint-4.yml):

- Checks the exact approved ancestry and unchanged original tests/migrations.
- Migrates an empty PostgreSQL **16** database and verifies Redis **7**, the restricted database role and Celery task registration.
- Runs the complete original backend suite plus integration regressions.
- Regenerates OpenAPI/TypeScript contracts, then runs zero-warning ESLint, TypeScript, production build, frontend unit tests and dependency audit.
- Seeds two isolated tenants and seven roles. Starts actual API, Celery worker/scheduler, Redis and the production frontend. Only external mail/model transports are substituted.
- Runs browser journeys against persisted records, auth/tenant/role boundaries, error paths, native dialogs, accessibility and the four required viewports.
- Scans correctness, dependencies, backend security and source secrets, and builds/inspects the non-root production backend image.
- Emits `CHECKPOINT 4 GATE: PASS` only after every mandatory step succeeds and records the exact SHA and test counts.

Local PostgreSQL is version 18; the mandatory PostgreSQL 16 proof comes from CI. Local Redis is version 7.4.11. Public CI artifacts contain test results and verified screenshots; generated fixture credentials, server secrets, browser storage and private runtime logs are excluded.

The requirement-to-code/test mapping is in [CHECKPOINT_4_TRACEABILITY.md](CHECKPOINT_4_TRACEABILITY.md). All original findings are tracked in [CHECKPOINT_4_FRONTEND_AUDIT.md](CHECKPOINT_4_FRONTEND_AUDIT.md). Any failed or skipped mandatory check blocks completion regardless of build success.

## Known Limitations

- Google/Microsoft live OAuth consent and production sending require the deployment's provider credentials and callback registration. Tests prove the real CRM chain with external-boundary substitutes; they do not certify a live provider account.
- Unsupported providers remain explicitly unavailable. Autonomous workforce functions and billing/payment execution remain out of scope.
- Campaign sender identity is set at creation; the current metadata editor changes persisted name/description only. Audience/content/sequence controls use the operations contract.
- Customer 360 and search retain the backend's documented section/result bounds. Picker pagination follows available backend list contracts; no browser-wide synthetic dataset is created.
- AI gateway outputs are suggestions. Usage can include unpriced requests; the UI does not fabricate cost or confidence values.
- Ambiguous external delivery requires provider reconciliation. Automatic resend is intentionally unavailable.
- Remaining production localStorage locations: **none**. The only sessionStorage item is expiring OAuth integration/tenant correlation metadata, never OAuth state, code or credentials. Deterministic data/providers exist only in test fixtures.
