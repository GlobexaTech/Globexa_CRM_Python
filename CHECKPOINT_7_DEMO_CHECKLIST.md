# Checkpoint 7 demo and acceptance checklist

Use an isolated test tenant and the restricted runtime role. Existing fixture scripts deliberately reject production databases. Never publish ignored runtime settings, fixture passwords or private logs.

1. Sign in as an owner and open Automations → Advanced workflow builder. Create a notification workflow, save its draft, validate, publish, execute and inspect its completed timeline. Reload and confirm persisted state.
2. Clone the workflow, change its draft and publish a new version. Confirm earlier executions retain their original version. Pause/resume and disable/archive it; verify state transitions prevent execution as designed.
3. Add conditions, waits and branches. Validate a cycle and a forward step-output reference and confirm rejection. Simulate bounded lead input. No model call occurs unless the model-assisted option is explicitly selected; no simulation sends or mutates CRM.
4. Run lead → score → condition → AI decision → independent review → AI draft → approved CRM draft → independently approved provider send. Inspect conversation state, three approval records and measured/unknown analytics.
5. Change a deal stage and confirm its outbox event creates exactly one execution. Inspect health, next-best-action reasoning and the approved task linked to that deal.
6. Ingest a provider message through the existing verified provider pipeline. Confirm classification, support draft, approvals, send and persisted provider-message ID.
7. Attempt self-approval, modified payload approval, cancelled execution approval, viewer mutation and cross-tenant reads. Confirm rejection and zero unauthorized effects.
8. Exercise a persisted wait, safe 429 with Retry-After, retry exhaustion and an uncertain webhook outcome. The uncertain outcome must never automatically replay.
9. Enforce execution and AI quotas; concurrent requests cannot both bypass a one-execution limit. Test explicit timezone, DST, month-end and holiday behavior.
10. Inspect the browser at 1440, 1280, 768 and 390 pixels. Run accessibility, lint, typecheck, build and the full existing browser suite.

Automated evidence: `tests/test_checkpoint7_engine.py` covers product flows and simulation; `tests/test_checkpoint7_security.py` covers hostile/failure boundaries; `tests/test_checkpoint7_expressions.py` covers conditions, schedules and graph safety; `frontend/tests/e2e/automation.spec.ts` covers persisted browser controls, tenant/RBAC boundaries and four viewports. The dedicated GitHub workflow also runs every prior backend/frontend test, clean PostgreSQL migrations, Docker and security scans.

Acceptance requires the exact pushed SHA's `CHECKPOINT_7_GATE.txt` artifact. The report identifies the verified baseline; each subsequent revision requires its own artifact before acceptance.
