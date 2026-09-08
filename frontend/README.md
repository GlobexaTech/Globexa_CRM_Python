# Globexa CRM frontend

The approved UI Lab is connected to the Python CRM through a Next.js backend-for-frontend (BFF). PostgreSQL is the source of CRM records, permissions, job outcomes, analytics and search. The application uses Next.js 16.3.3, React 19.2.8, TypeScript, TanStack Query, Arial and the existing local Globexa logo.

## Configuration and startup

Use Node.js 24, the versions in package-lock.json, a migrated Python backend and Redis 7. The backend must include the Checkpoint 4 contract fixes, including GET /api/v1/auth/permissions. The unchanged Checkpoint 3 SHA alone does not provide that endpoint; consult the Checkpoint 4 report for the exact backend differences and gate result.

From frontend, run npm ci and copy .env.example to .env.local. Supply these variables through private server configuration; never prefix them with NEXT_PUBLIC_.

| Variable | Meaning |
| --- | --- |
| APP_ORIGIN | Exact public HTTPS origin, for example https://crm.example.com. No trailing slash or path. Used for mutation-origin checks. |
| BACKEND_API_URL | Fixed Python API origin, for example http://backend:8000. No trailing slash or /api/v1 suffix. |
| FRONTEND_REDIS_URL | Redis database dedicated to frontend sessions, for example redis://127.0.0.1:6379/13. Use private networking and the authentication/TLS configuration required by the deployment. |
| SESSION_ENCRYPTION_KEY | Private 32-byte key encoded as 64 hexadecimal characters. Every frontend instance serving the deployment must use the same key. |
| FRONTEND_ENV | Omit in production. The literal value testing permits HTTP cookies for isolated local/CI verification. |

Generate the session key directly into private configuration. Rotating it invalidates existing frontend sessions. Real Gmail/Outlook secrets, provider credentials, AI configuration and CRM entitlements belong on the Python backend.

```sh
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

Serve the application behind HTTPS at APP_ORIGIN, preserving the browser Origin header. The Next.js server must reach the configured backend and Redis. This application requires its Node.js server routes; it is not a static export. Browser requests stay on the frontend origin.

For development against a nonproduction backend, explicitly set APP_ORIGIN=http://127.0.0.1:3000 and FRONTEND_ENV=testing, then run npm run dev -- --hostname 127.0.0.1. Production cookies always require HTTPS.

## Authentication and tenant boundaries

1. POST /api/session calls the real backend form-encoded login endpoint, then validates identity, memberships and permissions through backend routes.
2. Backend access/refresh tokens and session metadata are encrypted with AES-256-GCM in Redis. Browser JavaScript receives only a safe session DTO. The cookie contains a random opaque identifier, with HttpOnly, SameSite=Lax, host-only scope and Secure in production. The production cookie name is __Host-globexa-session. Sessions have an eight-hour absolute lifetime.
3. /api/crm accepts approved CRM paths plus the exact authenticated /auth/me profile path. The server supplies Authorization and X-Tenant-ID; browser authorization/tenant headers are not forwarded. Token and tenant query overrides are rejected.
4. Mutations require an exact matching Origin. Every CRM request carries a workspace version verified against the server session. Backend permissions and PostgreSQL RLS remain authoritative.
5. Workspace changes validate membership and call the real backend switch-tenant endpoint. The browser cancels requests, removes tenant query/mutation state, changes its generation and remounts workspace content. Late results from the prior generation are rejected. Cross-tab messages contain invalidation hints only.
6. Redis locks serialize refresh, workspace transitions and proxied requests across frontend instances. Redis commands have a three-second deadline and do not queue offline. Backend calls have an eight-second timeout; the browser client defaults to thirty seconds. A timeout can occur after a mutation reached the backend, so the UI asks the user to check saved/job state before retrying.
7. Only a backend authentication rejection can cause one bounded replay after refresh. Network timeouts and uncertain writes do not automatically replay. Durable operations use backend idempotency keys and display queued, running, completed, failed, unknown or unavailable states.
8. Logout deletes the Redis session before contacting the backend and clears the cookie even if that backend call fails. If Redis itself is unavailable, the browser clears local state and explicitly reports that server sign-out was not confirmed. The existing backend logout records an audit event; it does not revoke every independently issued JWT outside this BFF session.

SessionProvider supplies session/loading/error/can/login/logout/switchTenant/refreshSession. The shared API client supplies typed get/post/put/patch/delete, cancellation, deadlines, field errors and Retry-After. Query keys contain tenant_id, version and path. Components use these boundaries rather than direct backend fetches or localStorage CRM stores.

An offline query reports a network error with a Try again action. After reconnecting, use that action to reload the resource. Queries attempt the transport so an offline browser cannot leave a newly opened resource indefinitely paused; mutations never replay automatically after a network failure.

## Contracts and checks

openapi.json is exported from the actual backend. src/api/generated.ts is generated from it, and domain services use its DTOs with explicit adapters. Regenerate after intentional contract changes and review the diff.

```sh
npm run generate:api
npm run lint
npm run typecheck
npm run build
```

Auth store tests use real Redis. Point FRONTEND_REDIS_URL at a disposable test database before npm run test:unit.

## Reproducible browser integration environment

The test bootstrap is separate from the production application. It refuses any APP_ENVIRONMENT other than testing and any database name outside the globexa_cp4 namespace. Run from the repository root with the project's Python environment and a migration-administrator connection to disposable PostgreSQL.

Example POSIX environment; use equivalent PowerShell $env: assignments on Windows:

```sh
export APP_ENVIRONMENT=testing
export DATABASE_HOST=127.0.0.1
export DATABASE_PORT=5432
export DATABASE_USERNAME=postgres
export DATABASE_NAME=globexa_cp4_local
# Supply DATABASE_PASSWORD privately for this disposable service.
export REDIS_HOST=127.0.0.1
export REDIS_PORT=6379
export CELERY_BROKER_URL=redis://127.0.0.1:6379/11
export CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/12
export FRONTEND_REDIS_URL=redis://127.0.0.1:6379/13
export APP_ORIGIN=http://127.0.0.1:3254
export BACKEND_API_URL=http://127.0.0.1:8004
python scripts/checkpoint4_fixture.py --bootstrap
```

Bootstrap applies real migrations, provisions a restricted runtime role and seeds two tenants, seven actual roles and related CRM records. Private generated test credentials are saved only in ignored evidence/fixture.json and evidence/runtime.env.json. Do not commit or publish either file. Re-seeding preserves encryption/session keys for the same isolated database and creates fresh tenant IDs without deleting data.

Build the frontend, then start these processes in separate terminals with APP_ENVIRONMENT=testing:

```sh
python scripts/checkpoint4_runtime.py api
python scripts/checkpoint4_runtime.py worker
python scripts/checkpoint4_runtime.py scheduler
python scripts/checkpoint4_runtime.py frontend
```

The launcher loads private generated settings and verifies the runtime cannot bypass RLS. Add --dev to the frontend command only for development. The scheduler queues real outbox and CRM tasks every two seconds. Only external paid-provider interfaces are substituted: mail delivery/OAuth/sync and the model provider. The real gateway, ledger, quotas, authorization, transactions, events and durable jobs execute. Test launchers are absent from the production backend Docker image.

From frontend:

```sh
npx playwright install chromium
npm run test:e2e
```

Browser tests run serially against the application, PostgreSQL and Redis. They cover actual roles, session recovery, tenant boundaries, CRM relationships, jobs, workflows, campaigns, provider lifecycle, controlled AI, settings/search, responsive views and accessibility. Test mail subjects can produce explicit failed/unknown outcomes at the external adapter boundary; production providers are unaffected.

Activate the project's Python environment before launching Playwright, or set `CP4_PYTHON` to that environment's Python executable. The quota test uses it to change and restore an entitlement in the isolated fixture database; it cannot run against a production database.

## Evidence and capability limits

Traces/videos are disabled to avoid recording authentication bodies. Raw Playwright failure DOM snapshots may still contain generated fixture passwords. Treat raw evidence as private. Before sharing CI results, run python scripts/checkpoint4_public_evidence.py from the repository root. It copies only an allowlist of redacted text/XML and explicit authenticated audit PNG screenshots to evidence/public-artifact; it never copies private fixtures, environment files, server logs, generic failure screenshots, HTML reports, DOM snapshots, traces or videos. CI uploads nothing when sanitization fails. Write the exact-SHA gate marker after sanitization. The CI gate is the authoritative release result.

Provider availability comes from the backend. Unconfigured channels show unavailable states, and AI requires configuration outside the isolated test runtime. Live paid-provider delivery and production deployment are separate from automated adapter results. Outbound attachment upload/sending remains unavailable. A button click is not proof of delivery; saved job/provider state supplies that proof.
