# GLOBEXA CRM OS — CHECKPOINT 4

# FRONTEND ↔ BACKEND PRODUCT INTEGRATION & FRONTEND STABILIZATION

You are now responsible for implementing Checkpoint 4 of Globexa CRM.

This is a production-oriented integration checkpoint.

The goal is NOT to redesign the frontend and NOT to build another backend from scratch.

The goal is to transform the existing Globexa CRM UI Lab from a localStorage visual prototype into a real, authenticated, tenant-aware CRM application connected to the verified Globexa CRM Python backend.

---

# 1. AUTHORITATIVE SOURCES

Use these sources in this exact priority order:

### SOURCE 1 — CURRENT FRONTEND

The complete frontend source:

`globexa_crm_ui_lab.zip`

This is the existing UI that must be preserved and evolved.

The Codex audit of this frontend is:

`UI_LAB_AUDIT.md`

Treat the findings in that audit as the baseline defect register.

### SOURCE 2 — BACKEND

Repository:

`GlobexaTech/Globexa_CRM_Python`

Checkpoint 3 branch:

`checkpoint-3-crm-os-core`

Verified SHA:

`0d030cf4d0f0f00cec05f443d91c41f44ee7ba43`

### SOURCE 3 — BACKEND CONTRACT

Use:

`FRONTEND_API_CONTRACT.md`

from the Checkpoint 3 backend.

### SOURCE 4 — ARCHITECTURE

Use the supplied Globexa CRM architecture specification.

Do not invent architecture requirements that are not supported by the architecture or backend.

---

# 2. MANDATORY BASELINE

Before modifying anything:

Verify the current frontend repository state.

Verify that the backend baseline is:

```text
0d030cf4d0f0f00cec05f443d91c41f44ee7ba43
```

Do NOT modify Checkpoint 3 backend code unless a genuine frontend/backend contract incompatibility is discovered.

If a backend change is absolutely necessary:

1. document why
2. make the smallest possible backward-compatible change
3. add backend regression tests
4. preserve all Checkpoint 2 and Checkpoint 3 security guarantees
5. clearly report the backend change

Do not silently alter backend behavior to make the frontend work.

---

# 3. CREATE THE CHECKPOINT 4 BRANCH

Create:

```text
checkpoint-4-frontend-integration
```

Base it on the current approved frontend source.

If the frontend is maintained in a separate repository, use that repository.

Do not merge into main/master automatically.

---

# 4. PRIMARY OBJECTIVE

Convert:

```text
CURRENT

React UI
 ↓
useState
 ↓
localStorage
 ↓
synthetic/demo data
```

into:

```text
TARGET

React UI
 ↓
Session/Auth
 ↓
Tenant Context
 ↓
Typed API Client
 ↓
Backend API
 ↓
PostgreSQL / Redis / Celery
 ↓
Events / Automation / AI
```

The backend must become the authoritative source of CRM data.

---

# 5. PRESERVE THE EXISTING DESIGN

This is extremely important.

DO NOT:

* rebuild the application from scratch
* replace the visual identity
* replace the navigation unnecessarily
* replace working components without reason
* introduce a new design system merely for preference
* remove existing pipeline functionality
* discard existing animations
* rewrite every page

Preserve:

* Globexa blue/white visual identity
* current sidebar/navigation
* cards
* pipeline visual language
* lead filters
* tables
* drawers
* dashboard style
* existing animations where appropriate

Improve only where the audit identifies a concrete defect.

---

# 6. REMOVE LOCALSTORAGE AS CRM SOURCE OF TRUTH

The following current localStorage stores are prototype storage and must no longer be authoritative:

```text
globexa-pipeline
globexa-stages
globexa-contacts
globexa-conversations
globexa-campaigns
globexa-tasks
globexa-automations
globexa-ai-agents
```

Replace them with backend data.

LocalStorage may only be used for explicitly approved client-side preferences such as:

* UI theme
* sidebar state
* non-sensitive display preferences

NEVER store:

* access tokens
* refresh tokens
* API keys
* OAuth credentials
* tenant secrets

without an explicit secure architecture decision.

---

# 7. BUILD A REAL FRONTEND ARCHITECTURE

Create a clean structure such as:

```text
src/
  api/
    client/
    endpoints/
    errors/
    types/
  auth/
  tenant/
  permissions/
  hooks/
  services/
  components/
  features/
  types/
  utils/
```

Adapt the exact structure to the existing project.

Do not create unnecessary abstraction layers.

---

# 8. TYPED API CLIENT

Implement one centralized API client.

It must support:

* GET
* POST
* PATCH
* PUT
* DELETE

Handle:

* base URL
* headers
* authentication
* X-Tenant-ID
* JSON
* errors
* retries where appropriate
* idempotency
* request cancellation
* timeouts where appropriate

Do not scatter raw HTTP calls throughout components.

---

# 9. API CONTRACT IS AUTHORITATIVE

Before implementing each service:

Read the actual backend route, schema and `FRONTEND_API_CONTRACT.md`.

Do not guess.

Explicitly map:

```text
Frontend Type
 ↓
Request DTO
 ↓
Backend Schema
 ↓
Response DTO
 ↓
Frontend View Model
```

Where backend and frontend terminology differs, create an explicit adapter.

Do not silently rename backend fields everywhere.

---

# 10. AUTHENTICATION

Implement actual authentication.

Required:

### Login

Connect to the actual backend authentication endpoint.

### Session restoration

On browser reload:

```text
Browser
 ↓
Session
 ↓
Validate/refresh
 ↓
Load user
 ↓
Load tenant memberships
 ↓
CRM
```

### Logout

Clear client state and terminate session appropriately.

### Refresh

Handle expired access credentials without infinite retry loops.

### 401

Redirect to login/session recovery.

### 403

Show a proper permission message.

Never treat 401/403 as generic success.

---

# 11. SECURE TOKEN HANDLING

Do not copy the existing localStorage pattern for credentials.

Use the backend's actual authentication contract.

Prefer secure browser session architecture where supported.

Never expose:

* backend secrets
* provider API keys
* OAuth client secrets
* encryption keys

to browser JavaScript.

---

# 12. TENANT CONTEXT

Implement tenant-aware frontend state.

The user must be able to:

* see available workspaces/tenants
* select a tenant
* switch tenant
* understand current tenant

Every backend request must use the correct tenant context.

Where required:

```text
X-Tenant-ID
```

must correspond to the authenticated tenant membership.

Do not trust a manually typed tenant ID.

---

# 13. TENANT SWITCHING

When tenant changes:

1. cancel/invalidate outstanding requests
2. clear tenant-scoped cache
3. obtain the correct backend session/token according to contract
4. set the new tenant
5. reload tenant-scoped data
6. prevent previous tenant data from appearing

Test:

```text
Tenant A
 ↓
switch
 ↓
Tenant B
```

There must be no stale Tenant A data visible.

---

# 14. RBAC

Use the backend's actual role/permission model.

Backend roles include:

```text
owner
admin
sales_manager
sales_executive
marketing
viewer
ai_agent
```

Do not invent frontend roles.

Implement permission-aware UI.

Examples:

* viewer cannot create/delete CRM data
* sales executive cannot launch campaigns
* marketing cannot modify deals/tasks unless backend grants permission
* AI agent only sees capabilities granted by backend
* owner/admin can manage permitted administrative functions

Frontend permission checks are UX protection only.

The backend remains authoritative.

---

# 15. CORE CRM API INTEGRATION

Connect the existing UI to real backend APIs.

## Dashboard

Replace local aggregation with backend data.

Display:

* KPIs
* pipeline summary
* tasks
* activities
* AI insights where available

Respect role restrictions.

---

# 16. LEADS

Replace localStorage lead CRUD with backend CRUD.

Implement:

* list
* search
* filtering
* pagination
* create
* update
* detail
* delete where permitted
* scoring
* timeline
* ownership
* contact/company relationships

Use backend UUIDs.

Do not use:

```text
Date.now()
```

as CRM IDs.

Map source enums correctly.

---

# 17. CONTACTS

Connect:

* list
* search
* filtering
* create
* update
* delete where permitted
* detail
* activities
* company relationship
* opt-out fields

Use actual backend schema.

Do not use a free-text company field where the backend expects `company_id`.

---

# 18. COMPANIES

Add the missing Companies UI.

Implement:

* list
* search
* create
* edit
* detail
* contacts
* deals
* activities

Use backend authorization and tenant isolation.

---

# 19. PIPELINE / DEALS

This is a major correction.

The existing UI currently treats lead cards as pipeline cards.

Do not continue this architecture.

Implement the real distinction:

```text
Lead
 ↓
Opportunity / Deal
 ↓
Pipeline
 ↓
Pipeline Stage
```

Support:

* pipeline selection
* stage columns
* deal cards
* title
* value
* currency
* owner
* related lead/contact/company
* stage movement
* drag/drop
* server persistence
* rollback on failure
* domain event handling

Use the actual backend deal move contract.

Do not assume drag/drop success until the backend confirms it.

---

# 20. TASKS

Connect:

* list
* create
* update
* delete where permitted
* status
* priority
* assignee
* due date
* lead/contact/deal relationship

Map backend status enums exactly:

```text
pending
in_progress
completed
cancelled
```

Do not use frontend-only labels as API values.

---

# 21. ACTIVITIES / TIMELINE

Implement actual backend activity/timeline data.

Activities must not be fabricated.

Connect activities to:

* leads
* contacts
* companies
* deals
* conversations
* campaigns
* tasks

---

# 22. CUSTOMER 360

Add the missing Customer 360 page.

It must aggregate:

* company
* contacts
* leads
* deals
* tasks
* notes
* activities
* conversations
* messages
* campaigns
* AI insights
* timeline

Use the actual backend aggregate endpoint.

Support:

* loading
* empty
* partial data
* permission filtering
* API errors
* pagination where applicable

---

# 23. CONVERSATIONS

Replace fabricated messages with backend conversations.

Implement:

* conversation list
* conversation detail
* participants
* messages
* inbound/outbound
* timestamps
* status
* unread state where backend supports it
* channel
* provider message ID
* send message

Do NOT display a locally generated message as successfully delivered.

---

# 24. MESSAGE SENDING

Use the actual backend send contract.

Required:

```text
Idempotency-Key
```

where required.

Handle:

```text
202 / pending
 ↓
job/status
 ↓
completed
```

or the exact backend contract if the endpoint returns another state.

If the provider operation is unknown:

Display:

```text
Delivery status pending verification
```

Do not automatically resend.

---

# 25. CAMPAIGNS

Replace demo campaign counters with backend campaigns.

Implement:

* campaign list
* create
* audience
* template
* sequence
* scheduling
* launch
* pause
* resume
* cancel
* statistics
* suppression
* unsubscribe handling
* delivery status

Do not use "Run Demo" as production behavior.

If demo mode is retained for UI development, it must be visibly separated from real CRM mode.

---

# 26. CAMPAIGN ASYNC STATE

Campaign execution may be durable/asynchronous.

Do not equate:

```text
HTTP success
```

with:

```text
campaign delivery complete
```

Show:

* scheduled
* running
* paused
* completed
* failed
* unknown/reconciliation

using backend-supported states.

---

# 27. AUTOMATION / WORKFLOWS

Replace free-text demo workflows with backend workflow definitions.

Implement:

### Triggers

Use backend-supported triggers.

### Conditions

Structured conditions.

### Actions

Structured approved actions.

Support:

* create task
* update lead
* update deal
* add note
* send email
* assign owner
* approved AI tool

Do NOT allow arbitrary code execution.

---

# 28. WORKFLOW EXECUTION

Display:

* enabled/disabled
* version
* execution history
* success
* failure
* retry
* execution details

Never increment a local "runs" counter.

Use backend execution logs.

---

# 29. INTEGRATIONS

Replace the 13 hardcoded provider cards with the backend provider capability/status model.

Implement the actual supported providers.

Current verified backend capability must be respected.

Do not claim a provider is connected merely because a button was clicked.

Provider status must come from backend.

---

# 30. OAUTH

Implement the actual OAuth lifecycle:

```text
Connect
 ↓
Backend authorization
 ↓
Provider
 ↓
Callback
 ↓
Backend
 ↓
Integration status
```

Never place OAuth client secrets in the frontend.

Handle:

* state mismatch
* cancelled authorization
* callback errors
* expired credentials
* refresh
* disconnect

---

# 31. UNSUPPORTED PROVIDERS

If a provider is not implemented or not configured:

show:

```text
Not available
```

or:

```text
Configuration required
```

Do NOT show:

```text
Connected
```

because the user clicked Connect.

Do not fake:

* WhatsApp
* Meta
* Instagram
* LinkedIn
* Google Ads
* Apollo

unless the backend genuinely supports the required operation.

---

# 32. CONTROLLED AI

Connect the existing backend controlled AI capabilities.

Implement:

* lead scoring
* lead summary
* next-best-action
* reply analysis
* campaign drafting
* proposal drafting

Use the backend AI Gateway.

Do not create a second frontend-specific AI engine.

---

# 33. AI REQUESTS

AI calls must:

* respect tenant
* respect permissions
* check entitlement
* handle usage limits
* show loading
* handle 202/job states where applicable
* handle failures
* show provenance where backend supplies it
* never expose provider secrets

Do not display synthetic AI results as real results.

---

# 34. AI WORKFORCE UI

The current AI Agents page contains concepts such as:

* Supervisor
* Research Head
* CTO Tech

These are future concepts.

Do NOT falsely represent them as autonomous backend agents if the backend does not expose such APIs.

Convert the current page into an accurate controlled-AI interface or clearly label future capabilities.

Autonomous AI Workforce belongs to a later checkpoint.

---

# 35. ANALYTICS

Replace local calculations with backend analytics endpoints.

Use the backend views:

* dashboard
* pipeline
* conversion
* campaigns
* activity
* AI

Do not calculate "conversion rate" from local stage labels.

Do not fabricate revenue.

Respect:

* time range
* currency
* missing values
* permissions

---

# 36. GLOBAL SEARCH

Add the missing Global Search UI.

Search:

* leads
* contacts
* companies
* deals
* tasks
* notes
* conversations
* messages
* campaigns
* agents

Implement:

* debounced search
* loading
* no results
* result type
* result navigation
* permissions
* tenant scope

Use the backend search contract.

---

# 37. SETTINGS / ADMIN

Add only the settings functionality actually supported by the backend.

At minimum investigate:

* user profile
* workspace/tenant
* memberships
* available integrations
* supported administrative settings

Do not invent security controls for which no backend API exists.

If a requested administrative function is unavailable, show:

```text
Not available in this release
```

rather than implementing a fake setting.

---

# 38. ERROR SYSTEM

Create one centralized API error handler.

Map:

```text
401
403
404
409
422
429
500
502
503
504
```

Handle network errors.

Handle:

* field validation errors
* business errors
* permission errors
* rate limits
* asynchronous job failures
* unknown external effects

Do not expose stack traces.

---

# 39. LOADING STATES

Use the existing reusable loading components where appropriate.

Every production screen needs:

* initial loading
* mutation loading
* disabled action state
* skeleton where useful
* empty state
* error state

Do not show fake records while loading real data.

---

# 40. DEMO DATA MODE

If demo mode is retained:

Create an explicit environment/config flag.

Example:

```text
NEXT_PUBLIC_DEMO_MODE
```

Only use this for development/demo environments.

Production mode must never silently fall back to seeded records when the API fails.

API failure must remain an API failure.

---

# 41. CACHE / DATA STATE

Implement appropriate server-state handling.

You may use the existing React architecture or introduce a suitable lightweight server-state library if justified.

Do not introduce a large state-management framework merely because it exists.

Requirements:

* cache
* invalidation
* mutation reconciliation
* request cancellation
* tenant-scoped keys
* logout cleanup
* tenant-switch cleanup

---

# 42. MOBILE REPAIR

Fix the documented mobile failures.

At:

```text
390×844
768×1024
```

the core CRM must remain usable.

Fix:

* sidebar
* tables
* forms
* pipeline
* conversations
* task controls
* workflow controls
* campaign controls

Implement:

* collapsible navigation
* responsive tables
* stacked mobile layouts
* conversation list/detail navigation
* responsive forms

Do not merely hide functionality.

---

# 43. LEAD DRAWER BUG

Fix the verified layering defect.

The audit identified a global CSS decoration/z-index interaction causing the drawer backdrop to intercept controls.

Scope the decorative pseudo-element CSS correctly.

Verify:

* drawer opens
* drawer buttons clickable
* backdrop works
* Escape closes
* focus enters drawer
* focus returns to trigger

---

# 44. ACCESSIBILITY

Fix the actual audited issues.

Required:

* accessible names
* labels
* select names
* button names
* dialog semantics
* keyboard navigation
* focus management
* Escape
* focus restoration
* accessible drag/drop alternative
* contrast

Do not remove visual styling simply to avoid the axe report.

Fix the underlying accessibility issue.

Run axe again.

---

# 45. REDUCED MOTION

Respect:

```text
prefers-reduced-motion
```

including:

* hero animation
* background pseudo-element animations
* smooth scrolling where relevant
* transitions that materially affect motion

---

# 46. VALIDATION

Implement real client validation for:

* email
* required fields
* dates
* numeric values
* currency
* campaign configuration
* workflow conditions/actions

Backend validation remains authoritative.

Never use client validation as a security boundary.

---

# 47. CONFIRMATION / DESTRUCTIVE ACTIONS

Use consistent confirmation for:

* delete
* disconnect
* campaign cancellation
* workflow disable/delete
* bulk operations

Do not immediately destroy important CRM data from a single click.

---

# 48. DEAD CONTROLS

Repair or remove misleading controls identified in the audit.

Examples:

* Pipeline "New Lead"
* Lead Drawer Task
* Lead Drawer Conversation
* phone/email actions
* Settings
* Help

Every visible control must either:

1. perform its intended action,
2. navigate to a real feature,
3. be disabled with an understandable explanation,
4. or be removed.

Never leave fake functionality in production UI.

---

# 49. LOGO / ASSET FIX

Correct the case-sensitive logo path:

Current issue:

```text
globexa-logo.jpg
```

Actual asset:

```text
Globexa-Logo.jpg
```

Verify the production image request returns successfully.

---

# 50. LINT

Fix all current ESLint errors.

Current audit result:

```text
16 errors
0 warnings
```

Do not disable rules simply to achieve a green result.

Do not add broad ESLint ignores.

Run:

```bash
npm run lint
```

and achieve:

```text
0 errors
0 warnings
```

unless a documented framework-generated warning cannot be removed.

---

# 51. TYPESCRIPT

Add a proper typecheck script if absent:

```text
npm run typecheck
```

It must execute:

```text
tsc --noEmit
```

Achieve zero TypeScript errors.

---

# 52. TESTING

The current frontend has no authored automated tests.

Add a real test suite.

Use an appropriate tool such as Playwright for browser E2E if compatible with the project.

At minimum test:

### Authentication

* login
* invalid login
* session restoration
* logout
* expired session

### Tenant

* tenant selection
* tenant switching
* tenant data isolation
* stale data clearing

### RBAC

* viewer
* marketing
* sales executive
* sales manager
* admin/owner

### Leads

* create
* update
* detail
* AI score
* task
* timeline

### Pipeline

* create deal
* drag stage
* backend persistence
* failure rollback

### Customer 360

* aggregate
* permissions
* timeline

### Conversations

* load
* send
* failure
* async status

### Campaigns

* create
* plan
* launch
* async status
* failure

### Automation

* create
* enable
* trigger
* execution
* failure

### Integrations

* provider list
* OAuth initiation
* callback error
* disconnect
* unsupported provider

### AI

* capability
* permission
* quota
* failure
* result

### Search

* search
* no results
* permission filtering

### Errors

* 401
* 403
* 404
* 409
* 422
* 429
* 5xx
* offline

### Responsive

At minimum:

```text
1440×900
1280×800
768×1024
390×844
```

---

# 53. BACKEND INTEGRATION TEST ENVIRONMENT

Where possible, E2E tests must run against:

* PostgreSQL 16
* Redis 7
* actual Checkpoint 3 backend

Do not replace backend behaviour with frontend mocks for the core CRM journeys.

External paid providers may be mocked behind their provider adapter boundary.

---

# 54. FRONTEND CI

Create:

```text
.github/workflows/checkpoint-4.yml
```

It must verify:

1. dependency installation
2. lint
3. typecheck
4. production build
5. frontend unit/component tests
6. backend startup
7. PostgreSQL
8. Redis
9. authentication
10. tenant handling
11. RBAC
12. CRM E2E tests
13. API contract compatibility
14. accessibility checks
15. responsive smoke tests
16. security scan
17. secret scan

---

# 55. BACKEND REGRESSION

If running frontend integration against the backend:

verify that Checkpoint 3 remains healthy.

The following must remain green:

* RLS
* tenant isolation
* credential encryption
* webhook security
* RBAC
* Celery tenant context
* AI permission controls
* audit logging
* existing backend tests

Do not weaken backend security to simplify frontend integration.

---

# 56. API CONTRACT VALIDATION

Generate or consume the backend OpenAPI schema.

Where practical, generate TypeScript types from the verified backend contract.

If generated types conflict with handwritten types:

prefer the verified backend contract.

Do not maintain duplicate conflicting entity definitions.

---

# 57. DATA MODEL RULE

Frontend models must distinguish:

```text
Lead
Contact
Company
Deal
Pipeline
PipelineStage
Task
Activity
Conversation
Message
Campaign
Workflow
Integration
AIRequest
Analytics
```

Do not collapse unrelated entities simply because the prototype used one local object.

---

# 58. NO FAKE SUCCESS

This rule is mandatory.

Never display:

```text
Connected
Sent
Completed
Executed
AI scored
Campaign launched
Workflow executed
Sync complete
```

unless the backend actually confirms the operation.

For pending operations show:

```text
Pending
Processing
Scheduled
Awaiting confirmation
```

according to the actual backend state.

For failures show a real failure state.

---

# 59. OBSERVABILITY

For frontend operations, capture useful non-sensitive diagnostic information.

Do NOT log:

* tokens
* passwords
* API keys
* OAuth secrets
* full sensitive customer payloads

Provide enough context to diagnose:

* endpoint
* operation
* request ID if available
* error code
* status

---

# 60. PERFORMANCE

Do not prematurely optimize.

However:

* avoid duplicate API calls
* avoid API waterfalls
* cancel obsolete requests
* debounce global search
* paginate server-side lists
* avoid rendering thousands of records at once
* avoid unnecessary client components
* avoid repeated state-effect loops

Preserve existing performance unless actual measurements show a problem.

---

# 61. FINAL FRONTEND ARCHITECTURE

The final application should conceptually look like:

```text
                    GLOBEXA CRM UI
                           |
        +------------------+------------------+
        |                  |                  |
      Auth              Tenant             RBAC
        |                  |                  |
        +------------------+------------------+
                           |
                    Typed API Client
                           |
       +-------------------+-------------------+
       |                   |                   |
      CRM               Operations            AI
       |                   |                   |
 Leads/Contacts        Campaigns           AI Gateway
 Companies/Deals       Workflows           AI Tools
 Tasks/Activities      Integrations
       |                   |
       +-------------------+
               |
        Backend API
               |
      PostgreSQL/Redis
               |
        Events/Celery
```

---

# 62. CHECKPOINT 4 ACCEPTANCE GATES

Do NOT declare Checkpoint 4 complete merely because the application builds.

All of the following must pass:

## Build

```text
npm run build
```

PASS

## TypeScript

```text
npm run typecheck
```

PASS

## Lint

```text
npm run lint
```

PASS

## Tests

All frontend tests PASS.

## Backend

Checkpoint 3 regression PASS.

## Authentication

Real login/session/logout PASS.

## Tenant

Tenant switching and isolation PASS.

## RBAC

Negative permission tests PASS.

## CRM

Real backend CRUD PASS.

## Pipeline

Deal stage movement persists PASS.

## Customer 360

Real aggregate PASS.

## Conversations

Real backend messages PASS.

## Campaign

Real lifecycle PASS.

## Automation

Real execution PASS.

## Integrations

Capability/status accurately represented PASS.

## AI

Controlled AI operations PASS.

## Search

Global search PASS.

## Analytics

Backend analytics PASS.

## Mobile

390×844 core journeys usable PASS.

## Accessibility

No unresolved high-impact accessibility defects.

## Security

No exposed secrets.

No client-side security bypass.

## Demo Data

No silent production fallback.

## CI

Checkpoint 4 GitHub Actions GREEN.

---

# 63. FINAL REPORT

Create:

```text
CHECKPOINT_4_REPORT.md
```

Include:

## Executive Summary

## Frontend Architecture

## Authentication

## Tenant Architecture

## RBAC

## API Client

## CRM Integration

## Customer 360

## Conversations

## Campaigns

## Automation

## Integrations

## Controlled AI

## Analytics

## Global Search

## Accessibility

## Responsive Design

## Security

## Testing

## CI

## Backend Changes

## Known Limitations

---

# 64. TRACEABILITY MATRIX

Create:

```text
CHECKPOINT_4_TRACEABILITY.md
```

Use:

| Requirement    | Source   | Frontend Implementation | Backend Endpoint | Test | Status |
| -------------- | -------- | ----------------------- | ---------------- | ---- | ------ |
| Authentication | Contract |                         |                  |      |        |
| Tenant         | Contract |                         |                  |      |        |
| RBAC           | Contract |                         |                  |      |        |
| Leads          | Contract |                         |                  |      |        |
| Contacts       | Contract |                         |                  |      |        |
| Companies      | Contract |                         |                  |      |        |
| Deals          | Contract |                         |                  |      |        |
| Customer360    | Contract |                         |                  |      |        |
| Conversations  | Contract |                         |                  |      |        |
| Campaigns      | Contract |                         |                  |      |        |
| Automation     | Contract |                         |                  |      |        |
| Integrations   | Contract |                         |                  |      |        |
| AI             | Contract |                         |                  |      |        |
| Analytics      | Contract |                         |                  |      |        |
| Search         | Contract |                         |                  |      |        |

Do not mark PASS without executable evidence.

---

# 65. FINAL UI AUDIT

After implementation rerun:

* browser screenshots
* axe
* mobile tests
* keyboard navigation
* focus tests
* network/API capture
* error-state tests

Compare against the original:

`UI_LAB_AUDIT.md`

Create:

```text
CHECKPOINT_4_FRONTEND_AUDIT.md
```

Include:

* original finding
* repair
* evidence
* final status

Every H01–H12 finding from the original audit must be explicitly addressed.

Every M01–M10 finding must be addressed or documented with a justified deferral.

Every L01–L05 finding should be addressed unless there is a concrete reason not to.

---

# 66. IMPORTANT SCOPE LIMIT

Do NOT implement the following as autonomous production capabilities in Checkpoint 4:

* autonomous AI Sales Agent
* autonomous Supervisor
* autonomous Research Agent
* unrestricted computer-control agent
* autonomous lead purchasing
* unrestricted cold outreach
* arbitrary code execution
* unrestricted SQL tools
* full billing/payment lifecycle
* unsupported live integrations

Checkpoint 4 is about making the existing CRM a real connected product.

AI Workforce comes later.

---

# 67. DO NOT FAKE UNSUPPORTED BACKEND FEATURES

If the backend does not expose an endpoint:

DO NOT invent a fake endpoint.

Instead:

1. identify the missing backend capability
2. determine whether it is required for Checkpoint 4
3. if required, make the smallest documented backend extension
4. add backend tests
5. preserve security
6. document the change

---

# 68. FINAL GIT REQUIREMENTS

Before finalizing:

```bash
git status
git diff
git log --oneline
```

Review all modifications.

Do not commit:

* `.env`
* secrets
* node_modules
* build output
* generated caches
* browser credentials
* provider tokens

Create meaningful commits.

At minimum:

```text
Checkpoint 4: frontend architecture and auth
Checkpoint 4: CRM backend integration
Checkpoint 4: workflows campaigns integrations AI
Checkpoint 4: accessibility responsive fixes
Checkpoint 4: E2E tests and CI
```

Squash only if the repository's contribution policy requires it.

---

# 69. FINAL GITHUB ACCEPTANCE

The final SHA must be the exact SHA tested by CI.

GitHub Actions must show:

```text
CHECKPOINT 4 GATE: PASS
```

Do not report success based on a previous SHA.

Do not report success based only on local testing.

---

# 70. FINAL RESPONSE

When finished, return:

1. Frontend repository
2. Branch
3. Base SHA
4. Final SHA
5. Backend SHA used
6. Number of frontend API services
7. Number of connected modules
8. Authentication result
9. Tenant result
10. RBAC result
11. CRM result
12. Customer 360 result
13. Conversations result
14. Campaign result
15. Automation result
16. Integration result
17. AI result
18. Analytics result
19. Search result
20. Remaining mock-data locations
21. Remaining localStorage locations
22. ESLint result
23. TypeScript result
24. Build result
25. Frontend test count
26. E2E test count
27. Accessibility result
28. Responsive result
29. Security scan result
30. Backend regression result
31. CI workflow run ID
32. Exact SHA tested by CI
33. Remaining limitations
34. Checkpoint 4 verdict

Only use:

```text
CHECKPOINT 4: COMPLETE
```

if every mandatory acceptance gate passes.

Otherwise use:

```text
CHECKPOINT 4: NOT COMPLETE
```

and list the exact blockers.

---

# MOST IMPORTANT ENGINEERING RULE

Do not optimize for the appearance of completion.

Optimize for a real working product.

A button connected to local state is not a CRM feature.

A page rendering mock data is not an API integration.

A "Connected" badge is not an integration.

A "Run" counter is not an executed workflow.

An AI button is not AI integration.

A green build is not product readiness.

The final proof must be:

```text
REAL USER
   ↓
AUTHENTICATED SESSION
   ↓
CORRECT TENANT
   ↓
AUTHORIZED ACTION
   ↓
FRONTEND API
   ↓
CHECKPOINT 3 BACKEND
   ↓
POSTGRESQL / REDIS / CELERY
   ↓
DOMAIN EVENT / OPERATION
   ↓
REAL RESULT
   ↓
FRONTEND UPDATED
```

Implement, test, document and verify the complete chain.
