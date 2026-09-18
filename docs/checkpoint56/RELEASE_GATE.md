# Checkpoint 5 + 6 release gate

`.github/workflows/checkpoint-5-6.yml` verifies the exact pushed revision with
PostgreSQL 16, Redis 7, the real API/Celery services and the production frontend.
The gate retains the Checkpoint 4 ancestor and existing browser coverage, adding
workforce, independent approval, tenant isolation and four-viewport accessibility
scenarios. Deterministic external provider/model adapters keep these checks
repeatable; the artifact explicitly does not claim live provider certification.

The gate requires at least 328 backend tests, 34 frontend units and 66 browser
tests, including the named Checkpoint 5/6 authentication, configuration, provider,
security, workforce and release-gate suites plus RLS. It rejects failures,
errors, skipped tests, missing scanner reports,
dependency vulnerabilities and any source-secret finding. Reports and deliberate
authenticated screenshots are copied through the strict public evidence
sanitizer. Private fixtures, credentials, runtime logs, DOM snapshots, traces and
generic failure screenshots are excluded. Each sanitizer run rebuilds its
validated output directory so stale PASS markers or private files cannot survive.

## Historical secret scan review

The full-history Gitleaks 8.30.1 scan remains enabled without broad exclusions.
`scripts/triage_history_secrets.py` recognizes exactly 22 individually reviewed
findings by immutable commit, file, rule, start/end line and scanner fingerprint:

- 17 documentation placeholders in `PHASE1_ACCESS.md` and `PHASE5_ACCESS.md` at
  `c2127ab53da5fd75158a8f66bdb296ba43acf1e2`.
- Four occurrences of the same explicitly test-only CI encryption literal in
  `.github/workflows/checkpoint-2.yml` and one synthetic JWT in
  `tests/test_security.py`, at `71fbc0cff4eafc935914f374951be3ad135cdaa6`.

No production credential was identified in those reviewed findings. The historical
static CI test key is **ROTATION REQUIRED if ever reused outside isolated CI**.
Current CI/runtime keys are generated rather than reusing that historical value.

Both the redacted raw history scan and the metadata-only classification report
are published. Unknown, altered, duplicate, missing or unredacted findings fail
triage. The release gate recomputes the classification and requires an exact
match with the published report: 17 documentation placeholders, five synthetic
test literals and zero unresolved findings. Scanner execution errors also fail.

Only a successful run for the final pushed SHA can produce
`CHECKPOINT_5_6_GATE.txt`; local test results or older workflow runs do not certify
a later revision.
