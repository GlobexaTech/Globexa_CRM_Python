# Checkpoint 3 frontend API contract

Canonical machine contract: `/openapi.json`, exported by `python scripts/validate_openapi.py` to `evidence/openapi.json` and included in the final CI artifact. Request models are in `app/schemas/operations.py`; complete route definitions are in `app/api/v1/operations.py`. The examples below use symbolic IDs; replace them with UUIDs returned from this tenant's API.

## Shared behavior

Send `Authorization: Bearer <access-token>` and `X-Tenant-ID: <tenant-uuid>` on authenticated requests. The token and active membership determine identity; changing a header does not grant another tenant's access. `/api/v1/operations` is abbreviated `OPS` below. Existing `/api/v1/leads`, `/contacts`, `/companies`, `/deals`, `/tasks`, `/campaigns`, `/integrations` CRUD routes remain the creation/editing entry points; follow their OpenAPI methods and schemas.

Async requests and tools require `Idempotency-Key` (8–100 characters). Generate one key per user intent and reuse it for a network retry. Same key with different payload returns 409. A 202 response means queued, not delivered. Poll `GET OPS/jobs/{id}` or list `GET OPS/jobs`; display pending/retry/running, completed, failed, cancelled, unknown and awaiting_approval distinctly. Show error_code on failure. Do not automatically retry `unknown`: an external provider may have accepted the send. Only failed automation/sync jobs allow the explicit retry endpoint, with the original actor and bounded attempts. AI hooks can use `POST OPS/jobs/{id}/approve` after review.

Lists use `{items, total, limit, offset}` where declared. Check the operation's OpenAPI bounds; typical limits are 1–100. Empty data is an empty collection, not an error. UUIDs and timestamps serialize as strings; send timezone-aware ISO 8601 timestamps. Unknown fields in strict operation inputs are rejected. Render user content and search snippets as text.

Errors retain the existing API envelope with detail: 401 authentication, 403 permission/entitlement, 404 absent or inaccessible scoped object, 409 state/idempotency conflict, 422 schema/argument failure, 429 rate limiting with Retry-After, 503 unavailable provider/configuration/dependency. A foreign tenant resource must not become a successful lookup. Buttons should follow permissions but backend checks remain authoritative.

## Screen and operation mapping

| Screen / flow | Contract |
| --- | --- |
| Customer 360 | GET OPS/customers/{kind}/{id}; kind is contacts, companies or leads. Same path + /timeline accepts pagination; POST + /export audits exports. Sections are permission filtered. |
| Conversations Hub | GET/POST OPS/conversations; GET OPS/conversations/{id}; GET/POST + /messages; POST + /read. Creation accepts subject, channel, customer relations, integration_id and up to 20 participants. Send accepts recipient/body, returns a job. |
| Campaign editor | Create existing campaign with name, type, sender_name and sender_email. PUT OPS/campaigns/{id}/plan accepts integration_id, contact_ids or company_id, subject, body and optional steps/trigger_event. |
| Campaign launch/schedule | POST OPS/campaigns/{id}/schedule with scheduled_at; POST + /launch, /pause, /resume or /cancel; GET + /statistics. Display persisted recipient outcomes. |
| Workflow editor | GET/POST OPS/workflows; GET/PUT OPS/workflows/{id}; PATCH + /enabled with enabled boolean; GET + /executions. Editing increments version and disables it. |
| Integrations | GET OPS/providers for capabilities; create existing integration with provider configuration; GET OPS/integrations/{id}/status. POST + /authorize returns authorization URL/state flow; frontend redirects to provider. |
| OAuth callback | Frontend receives provider code/state and POSTs both to OPS/integrations/{id}/callback using the initiating user's authenticated session. Never send client secrets. POST + /refresh, /disconnect or /sync for lifecycle. Sync returns a job. |
| AI panel | POST OPS/ai/requests with capability/entity_id; POST OPS/ai/batches with requests array (maximum 25). Poll returned job IDs; fetch created proposal via GET OPS/proposals/{id}. |
| Jobs and approvals | GET OPS/jobs and /jobs/{id}; POST /jobs/{id}/approve or /retry when applicable. Never render raw job input as an administrative credential view. |
| Dashboard/reporting | GET OPS/analytics/{view}; view dashboard/pipeline/conversion/campaigns/activity/ai; optional aware start/end timestamps. |
| Global search | GET OPS/search?q=...&entity=leads&limit=20&offset=0; omit entity for permission-filtered cross-module results. Each result has entity/id/title/snippet/rank. |
| Tasks/activities | Existing task CRUD; POST OPS/activities with subject, optional description and at least one lead/deal/contact/company relation. |
| Approved assistant tools | POST OPS/tools/{name} with arguments object and Idempotency-Key. Tool-specific schemas/permissions are enforced in shared services. |
| Operator replay | POST OPS/events/{id}/retry requires audit:logs; persisted subscriber receipts suppress repeated effects. |

## Workflow example

POST `OPS/workflows`:

```json
{
  "name": "New lead follow-up",
  "trigger": "lead.created",
  "conditions": [],
  "actions": [{
    "tool": "create_task",
    "arguments": {"title": "Review new lead", "lead_id": "$event.id"}
  }]
}
```

Enable with PATCH `/workflows/{id}/enabled` and `{"enabled":true}` after reviewing its definition. Conditions permit status/stage_id/ai_score/value/source/direction with eq/ne/gt/lt. Action names: create_task, update_lead, update_deal, add_note, send_email, assign_owner, invoke_ai. Schema/action errors are visible failures; no arbitrary expressions or executable scripts are supported.

## AI example and review

POST `OPS/ai/requests` with `{"capability":"lead_score","entity_id":"<lead-uuid>"}`. Supported capabilities also include lead_summary, next_best_action, reply_analysis, campaign_draft and proposal_draft. Use the appropriate scoped entity for each capability (see OpenAPI/service definitions). Job results identify persisted insight/proposal records. Lead scores include bounded confidence and reasons; model-generated text is a draft/recommendation. Sending a draft requires the explicit normal send flow and its permissions/quota.

## Permissions and feature gates

Customer sections require the relevant module read permission. Conversations use conversations:read/write/send; workflows use automation:read/write and each action's permission; provider management uses integrations:read/write; AI execution requires ai:chat plus capability/entity permissions; analytics requires analytics:read (and view-specific access), campaigns their existing audience/template/sequence/send permissions; exports require leads:export. Use current role permissions from the server, not hard-coded role hierarchy assumptions. Quota-denied operations must show upgrade/admin guidance without resubmitting indefinitely.

Unread counts are conversation-wide. Message attachments currently describe inbound metadata; outbound attachment requests are rejected. Provider capability cards must disable unsupported WhatsApp/Meta/Instagram/LinkedIn/Google Ads/Apollo operations. Gmail/Outlook require configured OAuth apps. Customer sections cap related records at 200; search caps candidates at 100 per entity and total describes this bounded set. These limits should be visible for users interpreting incomplete histories or result counts.

Legacy raw AI POST endpoints and the raw integration-sync endpoint now return 410 with the supported operation path. Update frontend callers to durable jobs. The public unsubscribe form is served at `/api/v1/unsubscribe?token=...`; GET only confirms and POST applies the preference. It does not use an access JWT or X-Tenant-ID.

## Contract test evidence

`tests/test_checkpoint3.py`, `tests/test_checkpoint3_ai.py` and `tests/test_checkpoint3_security.py` contain 53 added tests. They exercise customer views, task/deal serialization, conversations and actual send/sync service contracts, campaign lifecycle/suppression/triggers, workflow execution/retry/permissions, OAuth isolation/replay/refresh/disconnect, six AI outputs/usage/failure paths, analytics views, all search entity types, quotas, rate limiting, OpenAPI and tenant isolation. PostgreSQL/RLS and Redis are real; external provider responses are controlled fixtures. A real Celery worker consumes a Redis-backed workflow job. The final CI artifact supplies the exact passing count and tested SHA.
