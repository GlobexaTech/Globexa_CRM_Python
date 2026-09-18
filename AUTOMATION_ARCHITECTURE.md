# Advanced automation architecture

Checkpoint 7 extends the existing FastAPI, SQLAlchemy/PostgreSQL, transactional outbox, Celery/Redis and Next.js application. It does not replace the earlier workflow or AI workforce services.

## Persistence and execution

Migration `018_advanced_automation` adds the ten required models: Automation, AutomationVersion, AutomationTrigger, AutomationCondition, AutomationAction, AutomationExecution, AutomationStepExecution, AutomationSchedule, AutomationVariable and AutomationCredentialReference. AutomationPolicy and AutomationNotification support limits and user notifications. ApprovalRequest and AIUsageLog reference the exact automation execution and step.

Drafts are mutable. Publication validates the graph and copies its full definition into an immutable numbered version and normalized child rows. Database triggers prevent published-row updates; the restricted runtime role cannot update or delete them. Executions retain their original version ID and digest across later publications.

CRM mutation → transactional DomainEvent → idempotent EventDelivery → AutomationExecution and OperationJob → one graph node per worker delivery. A step's internal mutation and completion commit atomically. AI and webhook calls commit a durable claim before crossing the external boundary. An interrupted external claim becomes unknown and cannot automatically replay. Messaging delegates to the existing provider job, exact approval and uncertain-outcome handling.

Execution states are QUEUED, RUNNING, WAITING, PAUSED, COMPLETED, FAILED, CANCELLED and EXPIRED. Step states are PENDING, RUNNING, WAITING, COMPLETED, FAILED and SKIPPED. Waits persist their deadline; workers never sleep. Safe transient errors use bounded exponential backoff, jitter and Retry-After. Failed steps retain a dead-letter record; continue/fallback is prohibited for authorization and uncertain-outcome failures.

The scheduler claims due rows with SKIP LOCKED, orders by deadline and excludes inactive workflows before applying its batch limit. Missed recurring slots coalesce into one execution; the next future slot is calculated in the persisted IANA timezone. DST gaps skip and repeated local times run once. Business-hour restrictions are checked when queuing and immediately before provider sending.

## Graph and limits

Conditions use dictionary traversal and a fixed operator allowlist, including AND/OR/NOT and change comparisons with recorded prior values. Templates substitute allowlisted scalar paths; no Python, shell, SQL or general template interpreter exists. Publication rejects graph cycles, unreachable steps and step-output dependencies that are not available on every path. Chained workflows use fixed IDs, publish-time chain validation and runtime visited/depth guards. Queued provider jobs carry chain ancestry into their resulting events.

Tenant advisory locks serialize admission, active-trigger capacity, rate accounting and AI quota reservations. At most 100 active workflows may share one trigger; publish and resume enforce this bound so the event consumer never silently truncates matches. Policy limits cover daily/monthly executions, queued executions, graph steps, depth, runtime, AI calls and tenant/action/provider rates. Messaging provider rates group by integration, webhook rates by host. Existing entitlements remain enforced.

## AI and intelligence

AI nodes return strict decision or intelligence schemas. Existing gateway routes record measured usage in an independent durable ledger. Unknown tokens and costs remain null; partial known cost is labeled separately. An explicitly configured alternate provider can serve as fallback. No model is implicitly purchased, downloaded or activated.

Lead scoring is explainable from persisted CRM relationships, state and activity. Duplicate candidates require review and are not merged. Deal health uses recorded stage age, ownership and overdue tasks. Customer 360 reuses its existing permission-checked aggregation. Campaign rates use persisted provider events; conversion remains unavailable without verified attribution. Outputs remain recommendations until an authorized action executes.

The simulator accepts bounded test facts. By default it stops honestly at undecided AI nodes. An explicit `use_model` request runs real structured model decisions under the same tenant limits and records usage, but never calls CRM mutation actions or messaging/webhook transports. Simulation output is labeled as test input.

## Product and operations

`/api/v1/automation` exposes catalog, policy, draft lifecycle, publication, version history, simulation, manual execution, timeline, notifications, intelligence and analytics. Lists use bounded pagination. `/automations/advanced` uses the existing authenticated BFF, workspace version fence, permission checks and design system. The earlier `/automations` workflow editor remains available.

Executions expose version, actor, event, chain and correlation IDs; steps expose timestamps, retries, errors, exact approval references and recorded outcomes. Operational logs never include provider tokens or raw provider error bodies. See AUTOMATION_SECURITY.md and CHECKPOINT_7_DEMO_CHECKLIST.md for release and operating checks.
