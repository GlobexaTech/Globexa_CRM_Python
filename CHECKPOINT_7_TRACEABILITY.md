# Checkpoint 7 traceability

Source of truth: `docs/checkpoint7/IMPLEMENTATION_BRIEF.md` (the supplied brief ends during section 55). Implementation paths below are repository-relative. The final exact-SHA gate remains the acceptance authority.

| Brief sections | Implementation | Evidence |
| --- | --- | --- |
| 1–2, 51–54: free tooling, diagnosis, honest provider limits, GitHub | Existing open-source stack; dedicated CP7 branch from verified CP5/6 SHA; explicit local/model configuration | WORK_LOG, SECURITY, dedicated CI gate |
| 3–5: persistent models, versions, states | `app/models/automation.py`, migration 018, `service.py`, `engine.py` | Restricted PostgreSQL lifecycle/version tests; clean CI migrations |
| 6–7: triggers and event execution | `core/events.py`, CRM subscriber, provider pipeline, Celery scheduler/jobs | Deal-stage event idempotency and inbound support flows |
| 8–9: conditions and operators | `expressions.py`, strict schemas, bounded trees | Parameterized operator/group/change tests |
| 10: reusable actions | `actions.py`, existing workforce tools and CRM/provider services | Real task/draft/send mutations and persisted messages |
| 11–14: idempotency, waits, retries, failure policies | Engine, OperationJob, step records, dead letters | Idempotency, wait/resume, safe webhook retry and unknown-outcome tests |
| 15–17: AI decisions/actions/safety | `ai.py`, existing gateway, strict output schemas, minimized context | Real usage ledger and decision branching; existing workforce security suite |
| 18: exact independent approval | Shared approval service and `automation/approvals.py` | Self-approval rejection, execution binding, cancellation and complete send flows |
| 19–20: variables/templates | Allowlisted scalar substitution and bounded render output | Injection/secret/path rejection, typed and HTML-escaped substitution tests |
| 21–24: rate/cost/quotas/loops | Policy, serialized admission/reservations, provider grouping, chain ancestry | Concurrent quota, AI quota, visited-chain and graph tests |
| 25–26: schedules/business hours | `scheduling.py`, due scheduler, final send-boundary check | DST/month/cron/holiday tests; queue integration |
| 27–28: API and validation | `api/v1/automation.py`, `validation.py`, immutable publication | API lifecycle, pagination, RBAC and browser persistence |
| 29–30: dry run/simulator | `service.simulate` and explicitly metered `simulate_with_model` | No CRM mutation, real AI decision and usage test; browser dry run |
| 31: analytics | `intelligence.analytics` | Lead flow counters, approval rates and unknown-cost assertions |
| 32–36: next action, lead/deal/customer/campaign intelligence | Permission-scoped persisted facts and existing Customer 360 | Deal/lead flows and prior customer/campaign suites; no fabricated conversion |
| 37–38: product frontend | Advanced workflow route, visual step builder, timeline, existing approval center/BFF | Browser save/publish/run/reload; four viewport accessibility checks |
| 39–42: RLS, SSRF, security defaults, audit | FORCE RLS, compound tenant keys, runtime checks, pinned webhook TLS, exact approvals | Prior full isolation/security suites plus CP7 failure-boundary tests/scans |
| 43–44: tests and three complete flows | Engine/security/expression/gate tests and browser tests | Required flow names enforced by CP7 gate |
| 45–46: bounded performance and observability | Indexed queue/state/parent keys, bounded graph/context/batches, paginated lists, execution/step/correlation records | Runtime tests and API pagination checks |
| 47–49: scans, CI, database | New migration only, dedicated workflow, Docker, Ruff/Bandit/dependency/secret scans | Exact-SHA CI artifact required |
| 50, 55: documentation and final report | Architecture, security, demo checklist, this matrix and report | Release report tied to the final pushed SHA |

AI memory and Supervisor remain the existing Checkpoint 6 services, with their full regression suite included. Provider adapters remain the Checkpoint 5 implementation. Live account certification is separate and requires credentials; synthetic external contract responses are not represented as live-provider results.
