GLOBEXA CRM — CHECKPOINT 7
ADVANCED AUTOMATION + INTELLIGENCE

Repository:
GlobexaTech/Globexa_CRM_Python

Branch:
checkpoint-7-advanced-automation-intelligence

Previous completed checkpoint:
CHECKPOINT 5 + 6 — Integrations + AI Workforce

IMPORTANT:
Before beginning Checkpoint 7, verify the actual final SHA of Checkpoint 5+6.

DO NOT assume Checkpoint 5+6 is complete merely because a previous
report says so.

Verify:

- Git branch
- final SHA
- migrations
- tests
- CI
- RLS
- tenant isolation
- AI tools
- agent executor
- approval workflow
- provider abstractions

If mandatory Checkpoint 5+6 requirements are still incomplete,
DO NOT rewrite them.

Fix only blockers that directly prevent Checkpoint 7.

============================================================
MISSION
============================================================

Build the Globexa CRM Advanced Automation + Intelligence layer.

The objective is to allow businesses to create automated workflows
that combine:

CRM events
+
conditions
+
delays
+
actions
+
AI decisions
+
human approval
+
external integrations
+
analytics

while maintaining:

tenant isolation
RBAC
auditability
idempotency
security
cost controls
failure recovery

The system must become an actual automation engine, not a collection
of hard-coded Celery tasks.

============================================================
1. FREE-FIRST POLICY
============================================================

Use only FREE/open-source resources wherever possible.

Prefer:

PostgreSQL
Redis
Celery
existing AI Gateway
existing NVIDIA access
existing DeepSeek access
local models
GitHub
Supabase free tier where appropriate
existing provider abstractions

Do NOT purchase services.

Do NOT activate billing.

If a feature genuinely requires a paid service:

STOP only that feature and report:

SERVICE:
WHY:
FREE ALTERNATIVE:
LOCAL ALTERNATIVE:
SUPABASE ALTERNATIVE:
COST:

Continue all other development.

============================================================
2. NEVER-GIVE-UP PROTOCOL
============================================================

Do not stop at the first error.

Use:

DIAGNOSE
→ FIX
→ TEST
→ VERIFY
→ CONTINUE

If one provider is unavailable, use a test double.

If AI provider returns 429:

retry with exponential backoff
→ provider fallback
→ local/free fallback where available
→ continue task

Never endlessly retry.

Never fabricate successful operations.

Never disable security to make automation work.

============================================================
3. AUTOMATION DATA MODEL
============================================================

Create persistent models for:

Automation
AutomationVersion
AutomationTrigger
AutomationCondition
AutomationAction
AutomationExecution
AutomationStepExecution
AutomationSchedule
AutomationVariable
AutomationCredentialReference

Use Alembic migrations.

Every tenant-owned model MUST include:

tenant_id

and appropriate RLS.

============================================================
4. AUTOMATION VERSIONING
============================================================

Automations must be versioned.

Never modify an automation version while it is executing.

Architecture:

Automation
 ↓
Version 1
Version 2
Version 3

An execution must always reference the exact automation version
that created it.

============================================================
5. AUTOMATION STATES
============================================================

Automation:

DRAFT
ACTIVE
PAUSED
DISABLED
ARCHIVED

Execution:

QUEUED
RUNNING
WAITING
PAUSED
COMPLETED
FAILED
CANCELLED
EXPIRED

Step:

PENDING
RUNNING
WAITING
COMPLETED
FAILED
SKIPPED

============================================================
6. TRIGGER ENGINE
============================================================

Implement triggers for:

lead.created
lead.updated
lead.stage_changed
contact.created
contact.updated
deal.created
deal.updated
deal.stage_changed
task.created
task.completed
message.received
message.sent
message.delivered
message.failed
campaign.completed
form.submitted
webhook.received
integration.connected
integration.disconnected
AI.score_changed

Also support:

scheduled trigger
manual trigger
API trigger

Every trigger must be:

tenant scoped
authenticated where applicable
idempotent
auditable

============================================================
7. EVENT BUS
============================================================

Use the existing domain-event architecture.

Required:

Domain Event
↓
Event Router
↓
Matching Automation
↓
Automation Execution
↓
Celery
↓
Step Executor

Do not run large automation workflows synchronously inside API requests.

============================================================
8. CONDITION ENGINE
============================================================

Implement conditions such as:

field equals
field not equals
contains
does not contain
starts with
ends with
greater than
less than
greater/equal
less/equal
is empty
is not empty
exists
changed
changed to
changed from

Support:

AND
OR
NOT

Example:

Lead score > 80
AND
Lead stage = Qualified

============================================================
9. CONDITION SECURITY
============================================================

Never allow automation conditions to execute arbitrary Python,
SQL or shell commands.

Conditions must operate against a controlled data model.

Do not evaluate user-supplied expressions with:

eval()
exec()

or equivalent unrestricted interpreters.

============================================================
10. ACTION ENGINE
============================================================

Implement actions:

create lead
update lead
create contact
update contact
create task
update task
create note
change deal stage
send email
send WhatsApp
add tag
remove tag
assign owner
start automation
stop automation
wait
AI analysis
AI scoring
AI research
request approval
webhook call
create notification

Actions must use the existing approved tool/provider architecture.

Do not duplicate provider authorization logic.

============================================================
11. ACTION IDEMPOTENCY
============================================================

Every consequential action must have an idempotency key.

Examples:

send email
send WhatsApp
create lead
create task
webhook

A retry must not accidentally execute the same external action twice.

============================================================
12. DELAY / WAIT ENGINE
============================================================

Implement:

wait seconds
wait minutes
wait hours
wait days
wait until date
wait until condition

Do NOT keep a Celery worker blocked while waiting.

Persist:

execution state
resume_at
step state

Then schedule/resume the execution later.

============================================================
13. RETRY ENGINE
============================================================

Implement:

retry count
maximum retries
backoff
jitter
retryable/non-retryable classification
dead-letter

Do not retry permanent errors indefinitely.

============================================================
14. AUTOMATION FAILURE HANDLING
============================================================

Support:

step retry
step failure
workflow failure
continue-on-error
stop-on-error
fallback action

Every failure must be persisted.

============================================================
15. AI DECISION NODE
============================================================

Implement an automation node:

AI Decision

Example:

Lead
↓
AI evaluates lead
↓
Qualified?
├── YES → Sales automation
└── NO → Nurture automation

AI decisions MUST return structured JSON matching a schema.

Never allow free-form AI text to directly control workflow execution.

============================================================
16. AI ACTION NODE
============================================================

Support:

AI summarize
AI classify
AI score
AI recommend
AI research
AI draft
AI extract structured information

AI output must be schema validated.

============================================================
17. AI SAFETY
============================================================

Automation AI must obey:

tenant isolation
RBAC
tool permissions
approval rules
data minimization
prompt-injection defenses

External content remains untrusted.

AI cannot:

change tenant
change permissions
disable approvals
export arbitrary data
execute arbitrary SQL
execute shell commands

============================================================
18. HUMAN APPROVAL NODE
============================================================

Automation must support:

AI/automation
↓
Approval Request
↓
Human
↓
Approve
OR
Reject
↓
Continue / Stop

Approval must reference:

automation execution
automation version
step execution
exact action payload

Changing the action after approval requires a new approval.

============================================================
19. AUTOMATION VARIABLES
============================================================

Support safe variables such as:

lead.first_name
lead.email
lead.score
deal.value
contact.company
current_user.name
automation.execution_id

Do NOT expose:

database passwords
OAuth tokens
API keys
environment variables

============================================================
20. TEMPLATE ENGINE
============================================================

Implement safe template substitution.

Example:

Hello {{lead.first_name}},

Do not use arbitrary Python expressions.

Protect against:

template injection
code execution
SQL injection
HTML injection

Sanitize output according to destination.

============================================================
21. RATE LIMITING
============================================================

Automations must respect provider limits.

Implement:

per-tenant limits
per-provider limits
per-action limits
AI usage limits

Respect provider Retry-After where available.

============================================================
22. AI COST CONTROL
============================================================

Implement tenant-level AI usage controls.

Track:

AI calls
tokens
estimated cost
agent
automation
execution
model

If provider does not provide usage:

record unknown/null.

Never fabricate cost.

Support configurable limits.

Example:

daily AI execution limit
monthly AI execution limit

When limit reached:

BLOCK
or
REQUIRE APPROVAL

Do not silently incur paid usage.

============================================================
23. AUTOMATION QUOTAS
============================================================

Implement safeguards for:

maximum executions
maximum steps
maximum recursion depth
maximum runtime
maximum queued executions
maximum AI calls per execution

Prevent infinite automation loops.

============================================================
24. LOOP DETECTION
============================================================

Prevent:

Automation A
→ Automation B
→ Automation A
→ Automation B

Implement:

execution chain ID
depth
visited automation/version tracking

Stop execution when configured limits are reached.

============================================================
25. SCHEDULE ENGINE
============================================================

Support:

one-time schedule
daily
weekly
monthly
custom cron where safe

Use timezone-aware scheduling.

Persist timezone.

Never assume UTC for user-local schedules.

============================================================
26. BUSINESS HOURS
============================================================

Support optional business-hours conditions:

working day
working hours
timezone
holiday handling where configured

Do not send external communications outside configured business
hours unless explicitly allowed.

============================================================
27. AUTOMATION BUILDER API
============================================================

Create backend APIs for:

create automation
get automation
update draft
publish
pause
resume
disable
archive
clone
validate
test
execute manually
view executions
retry execution
cancel execution

Enforce:

tenant
RBAC
ownership
audit

============================================================
28. AUTOMATION VALIDATOR
============================================================

Before publishing:

validate trigger
validate conditions
validate action schemas
validate referenced fields
validate providers
validate approval requirements
validate AI configuration
validate loops
validate quotas
validate credentials/configuration

A broken automation must not be published.

============================================================
29. DRY-RUN MODE
============================================================

Implement:

Test Automation

without executing consequential external actions.

Example:

Lead
→ condition
→ AI decision
→ draft email

Show:

what would happen
which conditions matched
which actions would execute

Do NOT send real email/WhatsApp in dry-run.

============================================================
30. AUTOMATION SIMULATOR
============================================================

Allow a user to supply test input:

lead
contact
deal
message

and simulate the workflow.

Return:

trigger result
condition results
AI decisions
planned actions
approval requirements

============================================================
31. ANALYTICS
============================================================

Implement automation analytics:

executions
success rate
failure rate
average duration
step duration
AI usage
provider usage
top failures
approval rate
conversion where data supports it

Do not fabricate metrics.

============================================================
32. NEXT-BEST-ACTION ENGINE
============================================================

Implement a recommendation service that can consider:

lead state
deal state
recent communication
tasks
campaign state
AI score
historical activity

Return structured recommendations:

action
reason
confidence
supporting data

Do not present AI recommendations as facts.

============================================================
33. LEAD INTELLIGENCE
============================================================

Implement:

lead scoring
lead classification
lead enrichment
lead prioritization
duplicate detection

Use explainable scoring inputs.

Never fabricate company/contact data.

============================================================
34. DEAL INTELLIGENCE
============================================================

Implement:

deal health
stalled-deal detection
stage duration
next action
risk indicators

Use actual CRM data.

============================================================
35. CUSTOMER INTELLIGENCE
============================================================

Customer 360 should aggregate:

contacts
deals
communications
tasks
campaigns
notes
AI summaries
activity

Respect tenant and RBAC.

============================================================
36. CAMPAIGN INTELLIGENCE
============================================================

Implement:

campaign performance
engagement
reply rates
conversion where data exists
AI-generated analysis

Do not invent unavailable statistics.

============================================================
37. AUTOMATION UI
============================================================

Extend the existing Next.js frontend.

Create:

Automation Dashboard
Automation Builder
Trigger selector
Condition builder
Action builder
AI node
Approval node
Delay node
Execution timeline
Execution details
Error details
Dry-run interface
Analytics

Use the existing Globexa design system.

Do not redesign unrelated pages.

============================================================
38. VISUAL AUTOMATION BUILDER
============================================================

If the frontend architecture supports a node-based builder:

Trigger
↓
Condition
↓
AI
↓
Approval
↓
Action
↓
Delay
↓
Action

Persist the workflow as structured JSON/schema.

Do not persist arbitrary executable code.

============================================================
39. AUTOMATION SECURITY
============================================================

Every automation execution must be:

tenant scoped
authorized
audited
idempotent

A user must not be able to execute another tenant's automation by
changing an automation ID.

Test:

Tenant A automation ID
used by Tenant B

Expected:

DENIED.

============================================================
40. WEBHOOK ACTION SECURITY
============================================================

Automation webhooks must prevent SSRF.

Only allow:

HTTPS
configured destinations
validated hosts

Block:

localhost
127.0.0.1
private networks
cloud metadata
internal services

Validate redirects.

============================================================
41. EXTERNAL ACTION APPROVAL
============================================================

Default to approval for:

bulk email
bulk WhatsApp
data export
delete operations
high-volume campaigns
sensitive customer actions

Allow administrators to configure approval policy.

The AI cannot disable this policy.

============================================================
42. AUDIT LOGGING
============================================================

Record:

automation created
automation updated
automation published
automation paused
automation executed
step executed
AI decision
approval requested
approval approved
approval rejected
external action
failure
retry
cancellation
configuration change

Never log secrets.

============================================================
43. TESTING
============================================================

Create and RUN tests for:

automation CRUD
versioning
publishing
validation
triggers
conditions
AND/OR/NOT
actions
idempotency
delays
retries
dead-letter
AI decisions
AI structured output
approval
variables
templates
rate limiting
quotas
loop detection
scheduling
timezone
dry-run
simulation
analytics
tenant isolation
RBAC
SSRF
prompt injection

============================================================
44. END-TO-END AUTOMATION TESTS
============================================================

Test:

Lead Created
↓
Lead Score
↓
Condition
↓
AI Decision
↓
Approval
↓
Draft Email
↓
Approval
↓
Provider test double
↓
Conversation update
↓
Analytics

Also test:

Deal Stage Changed
↓
Deal Health
↓
Next Best Action
↓
Task Creation

Also:

Inbound Message
↓
AI Classification
↓
Support Automation
↓
Suggested Response
↓
Approval
↓
Send

============================================================
45. PERFORMANCE
============================================================

Prevent:

N+1 queries
unbounded automation execution
unbounded queue growth
unbounded AI calls

Add pagination.

Use indexes for:

tenant_id
automation_id
execution_id
status
scheduled_at
created_at

============================================================
46. OBSERVABILITY
============================================================

Every execution should have:

execution_id
automation_id
version
tenant_id
correlation_id
started_at
completed_at
duration
status

Every step should have:

step_execution_id
step
status
duration
error
retry_count

Never log credentials.

============================================================
47. SECURITY SCANS
============================================================

Run:

Bandit
pip-audit
Gitleaks
npm audit

Do not suppress high/critical findings.

============================================================
48. CI
============================================================

Update/create:

.github/workflows/checkpoint-7.yml

Run:

backend tests
frontend tests
automation tests
security tests
RLS tests
E2E
lint
typecheck
Bandit
pip-audit
Gitleaks
npm audit

CI must fail on mandatory failures.

============================================================
49. MIGRATIONS
============================================================

Create proper Alembic migration(s).

Never modify historical migrations merely to make tests pass.

All new tenant-owned automation tables require:

tenant_id
RLS
FORCE RLS
appropriate policies

Verify migration on a clean database.

============================================================
50. DOCUMENTATION
============================================================

Create:

CHECKPOINT_7_REPORT.md
CHECKPOINT_7_TRACEABILITY.md
CHECKPOINT_7_DEMO_CHECKLIST.md
AUTOMATION_ARCHITECTURE.md
AUTOMATION_SECURITY.md

Document:

architecture
data model
execution engine
triggers
conditions
actions
AI nodes
approval
retry
idempotency
quotas
loop detection
security
testing
deployment

============================================================
51. PROVIDER CREDENTIAL POLICY
============================================================

Do NOT block Checkpoint 7 development because real provider credentials
are unavailable.

Use test doubles.

For any feature requiring a live provider:

IMPLEMENTATION:
PASS

AUTOMATED TEST:
PASS

PROVIDER-READY:
PASS/FAIL

LIVE CERTIFICATION:
BLOCKED — CREDENTIAL REQUIRED

Never fabricate live results.

============================================================
52. GITHUB
============================================================

Create:

checkpoint-7-advanced-automation-intelligence

from the verified Checkpoint 5+6 final SHA.

Do not begin from an unverified branch.

Push all completed work.

============================================================
53. NEVER-GIVE-UP
============================================================

If anything fails:

diagnose
→ fix
→ rerun
→ verify
→ continue

Do not stop at:

database failure
dependency failure
test failure
AI provider 429
provider credential absence
Docker failure

Use safe free alternatives.

Do not:

disable security
remove tests
suppress vulnerabilities
fabricate provider responses
purchase services
expose secrets
delete unrelated data

============================================================
54. NO FALSE COMPLETION
============================================================

Do not declare:

CHECKPOINT 7 COMPLETE

because the code exists.

Completion requires:

implementation
+
migration
+
tests
+
security tests
+
E2E
+
CI
+
documentation
+
GitHub push

Every PASS requires evidence.

============================================================
55. FINAL REPORT
============================================================

Return:

Repository:
Branch:
Base SHA:
Final SHA:
Remote SHA:

Database:
Migration:
RLS:

Automation Models:
Automation Engine:
Triggers:
Conditions:
Actions:
Delays:
Retries:
Idempotency:
Loop Detection:
Scheduling:
Timezone:
Quotas:

AI Decision:
AI Actions:
AI Cost Controls:
AI Memory:

Approval:
Supervisor:

Next Best Action:
Lead Intelligence:
Deal Intelligence:
Customer 360:
Campaign Intelligence:

Frontend:
Automation Builder:
Dry Run:
Simulator: