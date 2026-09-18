# Checkpoint 6 AI workforce and security contracts

The six agents (`research`, `lead_mining`, `sales`, `analyst`, `support`,
`supervisor`) execute persisted work using the existing PostgreSQL operation queue
and real Celery workers. `POST /api/v1/workforce/executions` returns a queued
execution, never a fabricated completed result. Execution states are queued,
running, completed, failed and cancelled. The scheduler recovers queued work;
uncertain model calls after worker loss are not silently repeated.

Each request records a verified tenant member as actor. Each worker, tool and
approval rechecks the current membership. An execution has at most three model
turns and eight tool actions. The model route is a server-configured `ModelRoute`
through the AI Gateway; clients cannot set a provider URL, tenant or permission.
Model output is strictly validated JSON. An unavailable model yields a visible
failed execution. It never yields a synthetic successful result.

## Model configuration

Use the existing server-only `CRM_AI_PROVIDER`, `CRM_AI_MODEL`,
`CRM_AI_BASE_URL` and `CRM_AI_API_KEY` settings. Local inference uses provider
`ollama` (`local` is an alias), an explicit installed model and the native Ollama
root URL, for example `http://127.0.0.1:11434`. This path requires no API key and
calls the [native chat API](https://docs.ollama.com/api/chat). An unavailable local
model fails visibly. Other configured providers require their server-side key.
The software does not buy credits, install models or provision a paid service.
Provider/model, measured tokens, latency, failure and execution ID are recorded
in the independent usage ledger. Missing token or cost measurements are NULL.
The analytics response includes `unmeasured_requests` and `unpriced_requests`.

## Tool and approval boundary

The approved tool names are:

- search_leads, get_lead, create_lead, update_lead
- search_contacts, get_customer, get_pipeline, get_deal
- create_task, update_task, create_note, get_conversation
- draft_email, send_email, search_analytics, research_web

An empty requested tools list means **no tools**. Each agent has a narrower
capability set; the caller must explicitly select permitted tools. Typed schemas
reject extra fields and nested identity overrides. Tools check current RBAC and
all referenced tenant-owned objects before reading or proposing a write.

All model-requested writes, including drafts, create persistent approval requests.
A different authorized human with `ai:approve` and the action's permissions must
decide. The requester cannot approve their own action and an AI service account
cannot approve. A SHA-256 digest binds canonical action type, arguments and
provider/conversation configuration. Recipient, content, target, attachments,
provider, subject or thread substitutions require a fresh approval. The worker
rechecks the digest, both humans' permissions and target configuration.
The approval also binds the sender configuration and a one-way credential-grant
fingerprint. Reconnection or token replacement conservatively requires a new
approval. The child send repeats approval, permission, body, recipient, queued
message and provider checks immediately before the external call. No credential
value is stored in approval JSON.

Send approval queues the existing message operation. Approval remains approved
while that child operation runs, then records executed or failed with the child
job and actual provider outcome. Sent is not delivered. Unknown delivery is never
automatically resent. Every mutation is idempotent under a tenant-scoped key and
PostgreSQL advisory locking.

The Supervisor uses the model to propose at most five independent subtasks,
inherits the requester's selected tools and context, queues persistent children,
monitors them and consolidates their actual results with another recorded model
call. It permits at most two retries of a known model-unavailable failure with
no tool effects. It cannot relax approvals or change tenant scope. A ten-minute
child-monitor deadline fails visibly and cancels remaining work.

## Memory and research

Working memory stores only execution metadata and tool names for 24 hours.
Long-term memory is explicit, requires a separate human approval and expires in
1–90 days. It is scoped to tenant, agent and originating actor. The API supports
physical deletion and the retention service deletes expired rows. Customer
messages, webpages and notes are not automatically copied into long-term memory.

Optional server settings (off/empty by default):

```dotenv
WORKFORCE_EVENT_TRIGGERS=false
WORKFORCE_RESEARCH_ALLOWED_HOSTS=
```

When opted in, `lead.created`, `message.received`, `deal.stage_changed` and
`campaign.completed` queue scoped analysis using the event actor. Event IDs fence
duplicates. Events with no accountable actor or insufficient permissions do not
gain an elevated system identity. Depth is bounded to prevent trigger loops.

Research requires both an administrator-approved hostname and exact URLs selected
by the requesting user in `context.research_urls`. It permits HTTPS port 443 only,
no credentials or query string, bounded textual content and at most three
redirects. Every redirect must itself be among the selected URLs. DNS addresses
must all be public; the socket pins a validated address while TLS validates the
original hostname. Loopback, private, unspecified, metadata and internal
addresses are rejected. Model-generated URLs cannot expand the fetch scope.
External content remains untrusted data; it cannot change system instructions,
identity, tool authorization or approval policy.

## Authentication and production operations

New JWTs carry random `jti`, session-family `sid` and a hard `session_exp`.
Both tokens from login share a family. Refresh is an atomic single-use Redis
operation. Replay revokes the family, including newer tokens. Backend logout
revokes its family while preserving independent logins. Requests check revocation
and current membership; Redis unavailability returns a safe 503 and fails closed.
No raw JWT or refresh-token plaintext is stored in Redis.

**Upgrade:** existing JWTs without the new claims are rejected. Users must sign in
again. BFF sessions that contain old tokens should be discarded during deployment.

**Redis durability:** production Redis must be private, authenticated and durable.
Enable AOF/persistence and appropriate backups; do not flush the authentication
keyspace. Revocation and refresh-consumption records must survive a restart for
the remaining session lifetime. If that keyspace is lost, rotate the JWT signing
key and require fresh login before accepting traffic. Redis failure itself never
falls back to accepting unchecked tokens.

Production configuration rejects debug/SQL echo, default or weak credentials,
missing encryption keys, unsafe CORS, public Redis for the application or Celery,
unauthenticated broker/result stores and non-JSON serializers. Private DNS must
resolve only to private/loopback addresses at startup; deployment network ACLs
must maintain this boundary. Database and Redis credential URLs escape reserved
characters. Production validation errors omit secret-bearing input values.

## Executed evidence

`tests/test_checkpoint6_workforce.py` exercises real restricted PostgreSQL
sessions, the actual gateway and independent usage ledger. Only external model
and provider transports are substituted. It includes both required chains:

1. Lead → research → AI score → sales recommendation → draft → independent
   approval → send → conversation → Customer 360.
2. Signed inbound WhatsApp webhook → persisted receipt → provider worker →
   conversation → support analysis → draft → independent approval → send →
   sent/delivered provider state.

The suite also executes all six agents, the sixteen-tool boundary, tampering,
self-approval, retention, concurrent idempotency, cancellation while a real model
call is in flight, prompt injection, SSRF and redirect validation.
`tests/test_checkpoint56_auth.py` exercises actual Redis rotation/revocation,
expiry, signed-role substitution, membership removal and outage fail-closed.
`tests/test_checkpoint56_config.py` executes production acceptance/rejection and
credential URL encoding. Run counts and final CI evidence belong in the release
report; these deterministic transports provide implementation evidence, not live
provider certification.
