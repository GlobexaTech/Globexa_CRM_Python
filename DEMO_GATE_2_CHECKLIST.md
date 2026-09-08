# Demo Gate 2 checklist

Status: NOT COMPLETE until the final branch SHA passes Checkpoint 2 Gate in GitHub Actions.

An unchecked item is not a PASS. CI artifacts bind evidence to the commit SHA and workflow run ID.

- [x] Required baseline SHA verified; baseline CI run 33722409634 passed.
- [x] All 21 original tests passed locally; original test files are unchanged.
- [x] Revised local suite: 56 tests passed, including restricted-role RLS, pool reuse and worker isolation.
- [x] Local migrations reached 010_auth_audit; 51 tenant_id tables and 2 identity/workspace tables have FORCE RLS.
- [x] Local Ruff correctness scan passed.
- [x] Local tracked-application Bandit scan has no findings.
- [x] Local pip-audit reports no known vulnerabilities.
- [ ] Final SHA: complete tests/security suite on PostgreSQL 16 and Redis 7 in CI.
- [ ] Final SHA: empty migrations and SQLAlchemy mappers in CI.
- [ ] Final SHA: Celery registration and Redis checks in CI.
- [ ] Final SHA: Ruff, Bandit, pip-audit and Gitleaks in CI.
- [ ] Final SHA: production image build, non-root UID and production-only dependencies.
- [ ] Final SHA: CI workflow run and evidence artifact verified.

Only mark Gate 2 COMPLETE after all checks pass for the final SHA. Keep master unchanged and do not begin Checkpoint 3 before that evidence is verified.
