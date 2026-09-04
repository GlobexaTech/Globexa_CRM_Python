# DEMO_GATE_2_CHECKLIST.md

## Globexa CRM — Checkpoint 2 / Gate 2 Verification Checklist

**Branch**: `checkpoint-2-security-hardening`  
**Base**: `checkpoint-1d-final-fixes` (SHA: `725acda5e4943d6c2ed9b1d7b47035a897c43c41`)  
**Date**: 2026-09-04

---

## Instructions

This checklist must be completed with **actual verification evidence** — not assumptions. Each item must be marked PASS only after the specified command has been executed and produced the expected result.

**Do not mark PASS based on code inspection alone. Run the commands.**

---

## 1. Baseline Verification (Checkpoint 1D Preserved)

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 1.1 | Git HEAD at Checkpoint 1D SHA | `git rev-parse HEAD` | `725acda5e4943d6c2ed9b1d7b47035a897c43c41` | ☐ |
| 1.2 | Python compilation | `python -m compileall app alembic demo.py` | No errors | ☐ |
| 1.3 | SQLAlchemy mappers | `python -c "from app.models import *; from sqlalchemy.orm import configure_mappers; configure_mappers(); print('MAPPERS_OK')"` | `MAPPERS_OK` | ☐ |
| 1.4 | Original 21 tests pass | `pytest -q` | `21 passed` | ☐ |

---

## 2. PostgreSQL RLS Implementation

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 2.1 | Migration 007 exists | `ls alembic/versions/007_rls_tenant_isolation.py` | File exists | ☐ |
| 2.2 | Alembic upgrade from empty DB | `docker compose up -d postgres redis && alembic upgrade head` | 7/7 migrations applied | ☐ |
| 2.3 | RLS enabled on all tenant tables | `psql -c "SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public' AND rowsecurity=true;"` | 37 tables listed | ☐ |
| 2.4 | FORCE RLS on critical tables | `psql -c "SELECT tablename, forcerowsecurity FROM pg_tables WHERE schemaname='public' AND forcerowsecurity=true;"` | 37 tables listed | ☐ |
| 2.5 | Policies exist (USING + WITH CHECK) | `psql -c "SELECT tablename, count(*) FROM pg_policies WHERE schemaname='public' GROUP BY tablename;"` | 2 policies per table (74 total) | ☐ |
| 2.6 | No duplicate policies | `psql -c "SELECT schemaname, tablename, policyname, count(*) FROM pg_policies GROUP BY schemaname, tablename, policyname HAVING count(*) > 1;"` | 0 rows | ☐ |
| 2.7 | Helper functions exist | `psql -c "\df set_tenant_context"` | Function exists | ☐ |

---

## 3. Cross-Tenant Isolation Tests (Real PostgreSQL)

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 3.1 | Tenant A cannot SELECT Tenant B | `pytest tests/test_security.py::TestTenantIsolation::test_cross_tenant_select -xvs` | PASS (blocked by RLS) | ☐ |
| 3.2 | Tenant A cannot INSERT Tenant B | `pytest tests/test_security.py::TestTenantIsolation::test_cross_tenant_insert -xvs` | PASS (blocked by RLS) | ☐ |
| 3.3 | Tenant A cannot UPDATE Tenant B | `pytest tests/test_security.py::TestTenantIsolation::test_cross_tenant_update -xvs` | PASS (blocked by RLS) | ☐ |
| 3.4 | Tenant A cannot DELETE Tenant B | `pytest tests/test_security.py::TestTenantIsolation::test_cross_tenant_delete -xvs` | PASS (blocked by RLS) | ☐ |
| 3.5 | Unfiltered ORM query isolated | `pytest tests/test_security.py::TestTenantIsolation::test_unfiltered_query -xvs` | PASS (RLS enforces) | ☐ |
| 3.6 | Aggregation doesn't leak | `pytest tests/test_security.py::TestTenantIsolation::test_aggregation -xvs` | PASS (RLS enforces) | ☐ |
| 3.7 | Cross-table joins isolated | `pytest tests/test_security.py::TestTenantIsolation::test_cross_tenant_join -xvs` | PASS (RLS enforces) | ☐ |
| 3.8 | Connection reuse no leak | `pytest tests/test_security.py::TestTenantIsolation::test_connection_reuse -xvs` | PASS (SET LOCAL works) | ☐ |

---

## 4. Credential Encryption

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 4.1 | Encryption service works | `python -c "from app.core.credential_encryption import encrypt_credentials, decrypt_credentials; d={'k':'v'}; e=encrypt_credentials(d); print(decrypt_credentials(e))"` | `{'k': 'v'}` | ☐ |
| 4.2 | AES-256-GCM used | `grep -r "AESGCM" app/core/credential_encryption.py` | Found | ☐ |
| 4.3 | HKDF key derivation | `grep -r "HKDF" app/core/credential_encryption.py` | Found | ☐ |
| 4.4 | Nonce + ciphertext + tag format | `grep -r "nonce.*ciphertext" app/core/credential_encryption.py` | Found | ☐ |
| 4.5 | Production key validation | `grep -r "SECURITY_CREDENTIAL_ENCRYPTION_KEY" app/core/config.py` | Validator exists | ☐ |
| 4.6 | No plaintext credential paths | `grep -r "json.dumps.*credential" app/ --include="*.py" | grep -v encrypted` | No results | ☐ |
| 4.7 | Tamper detection works | `pytest tests/test_security.py::TestCredentialEncryption::test_decrypt_tampered_data_raises -xvs` | PASS | ☐ |
| 4.8 | Wrong key rejected | `pytest tests/test_security.py::TestCredentialEncryption::test_decrypt_wrong_key_raises -xvs` | PASS | ☐ |

---

## 5. Webhook Security

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 5.1 | Meta verifier implemented | `grep -r "MetaWebhookVerifier" app/core/webhook_security.py` | Class exists | ☐ |
| 5.2 | WhatsApp verifier implemented | `grep -r "WhatsAppWebhookVerifier" app/core/webhook_security.py` | Class exists | ☐ |
| 5.3 | Stripe verifier implemented | `grep -r "StripeWebhookVerifier" app/core/webhook_security.py` | Class exists | ☐ |
| 5.4 | Generic HMAC verifier | `grep -r "GenericHMACVerifier" app/core/webhook_security.py` | Class exists | ☐ |
| 5.5 | Constant-time comparison | `grep -r "compare_digest" app/core/webhook_security.py` | Used | ☐ |
| 5.6 | Timestamp validation (Stripe) | `grep -r "timestamp.*300" app/core/webhook_security.py` | 5-min window | ☐ |
| 5.7 | Payload size limits | `grep -r "max_body_size" app/core/webhook_security.py` | 1MB default | ☐ |
| 5.8 | Meta signature verification test | `pytest tests/test_security.py::TestWebhookSecurity::test_meta_verifier_valid_signature -xvs` | PASS | ☐ |
| 5.9 | Invalid signature rejected | `pytest tests/test_security.py::TestWebhookSecurity::test_meta_verifier_invalid_signature -xvs` | PASS | ☐ |
| 5.10 | Missing signature rejected | `pytest tests/test_security.py::TestWebhookSecurity::test_meta_verifier_missing_signature -xvs` | PASS | ☐ |
| 5.11 | Stripe valid signature test | `pytest tests/test_security.py::TestWebhookSecurity::test_stripe_verifier_valid_signature -xvs` | PASS | ☐ |
| 5.12 | Stripe expired timestamp rejected | `pytest tests/test_security.py::TestWebhookSecurity::test_stripe_verifier_expired_timestamp -xvs` | PASS | ☐ |
| 5.13 | No legacy unsigned webhook routes | `grep -r "webhook.*POST" app/api/v1/webhooks/router.py | grep -v verify` | All routes verify | ☐ |

---

## 6. Webhook Replay Protection

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 6.1 | Redis SET NX EX used | `grep -r "set.*nx.*ex" app/core/webhook_security.py` | Found | ☐ |
| 6.2 | Meta leadgen_id for replay key | `grep -r "leadgen_id" app/core/webhook_security.py` | Used | ☐ |
| 6.3 | Replay protection test | `pytest tests/test_security.py::TestWebhookSecurity::test_replay_protection -xvs` | PASS | ☐ |
| 6.4 | Different event same source allowed | Manual test: send two different leadgen_ids | Both accepted | ☐ |
| 6.5 | Replay key TTL configured | `grep -r "86400" app/core/webhook_security.py` | 24 hours | ☐ |

---

## 7. API Rate Limiting

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 7.1 | RateLimiter class exists | `grep -r "class RateLimiter" app/core/rate_limiter.py` | Found | ☐ |
| 7.2 | IP scope implemented | `grep -r "RateLimitScope.IP" app/core/rate_limiter.py` | Found | ☐ |
| 7.3 | User scope implemented | `grep -r "RateLimitScope.USER" app/core/rate_limiter.py` | Found | ☐ |
| 7.4 | Tenant scope implemented | `grep -r "RateLimitScope.TENANT" app/core/rate_limiter.py` | Found | ☐ |
| 7.5 | Endpoint scope implemented | `grep -r "RateLimitScope.ENDPOINT" app/core/rate_limiter.py` | Found | ☐ |
| 7.6 | Login rate limit (5/5min) | `grep -r "max_requests=5" app/core/rate_limiter.py` | Found | ☐ |
| 7.7 | Sliding window with Redis sorted sets | `grep -r "zadd\|zremrangebyscore" app/core/rate_limiter.py` | Found | ☐ |
| 7.8 | Rate limit headers returned | `grep -r "X-RateLimit" app/core/rate_limiter.py` | All 4 headers | ☐ |
| 7.9 | 429 response with Retry-After | `grep -r "Retry-After" app/core/rate_limiter.py` | Found | ☐ |
| 7.10 | Health endpoints excluded | `grep -r "health.*skip\|health.*exclude" app/core/rate_limiter.py` | Excluded | ☐ |
| 7.11 | Middleware registered in main.py | `grep -r "rate_limit_middleware" app/main.py` | Registered | ☐ |
| 7.12 | Rate limit test passes | `pytest tests/test_security.py::TestRateLimiter -xvs` | All PASS | ☐ |

---

## 8. Authentication & Refresh Token Security

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 8.1 | RefreshTokenService exists | `grep -r "class RefreshTokenService" app/core/refresh_token.py` | Found | ☐ |
| 8.2 | Unique JTI per token | `grep -r "jti" app/core/refresh_token.py` | Used | ☐ |
| 8.3 | Token families implemented | `grep -r "family_id" app/core/refresh_token.py` | Found | ☐ |
| 8.4 | Token rotation on use | `grep -r "replaced_by" app/core/refresh_token.py` | Found | ☐ |
| 8.5 | Reuse detection revokes family | `grep -r "reuse detected" app/core/refresh_token.py` | Found | ☐ |
| 8.6 | Tokens stored as hashes | `grep -r "_hash_token" app/core/refresh_token.py` | SHA256 with salt | ☐ |
| 8.7 | Revoke single token | `grep -r "revoke_token" app/core/refresh_token.py` | Method exists | ☐ |
| 8.8 | Revoke family | `grep -r "revoke_family" app/core/refresh_token.py` | Method exists | ☐ |
| 8.9 | Revoke all user tokens | `grep -r "revoke_all_user_tokens" app/core/refresh_token.py` | Method exists | ☐ |
| 8.10 | Rotation test passes | `pytest tests/test_security.py::TestRefreshTokenService::test_verify_and_rotate_success -xvs` | PASS | ☐ |
| 8.11 | Reuse detection test passes | `pytest tests/test_security.py::TestRefreshTokenService::test_reuse_detection_revokes_family -xvs` | PASS | ☐ |
| 8.12 | Expired token rejected | `pytest tests/test_security.py::TestRefreshTokenService::test_expired_token_raises -xvs` | PASS | ☐ |

---

## 9. RBAC & Privilege Escalation Prevention

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 9.1 | Single RBAC module | `ls app/core/rbac.py` | Exists | ☐ |
| 9.2 | 60+ permissions defined | `grep -c "class Permission" app/core/rbac.py` | > 60 | ☐ |
| 9.3 | 6 roles defined | `grep -c "class RoleEnum" app/models/__init__.py` | 6 (OWNER..VIEWER) | ☐ |
| 9.4 | OWNER has SUPERUSER_ALL | `pytest tests/test_security.py::TestRBAC::test_owner_has_all_permissions -xvs` | PASS | ☐ |
| 9.5 | ADMIN cannot assign OWNER | `pytest tests/test_security.py::TestRBAC::test_can_assign_role -xvs` | PASS | ☐ |
| 9.6 | SALES_MANAGER cannot assign roles | `pytest tests/test_security.py::TestRBAC::test_can_assign_role -xvs` | PASS | ☐ |
| 9.7 | Self-escalation blocked | `pytest tests/test_security.py::TestRBAC::test_can_manage_membership -xvs` | PASS | ☐ |
| 9.8 | Last OWNER protection | Code review: check `can_manage_membership` logic | Implemented | ☐ |
| 9.9 | FastAPI dependencies exist | `grep -r "require_permission\|require_role" app/core/rbac.py` | Found | ☐ |
| 9.10 | No duplicate RBAC in deps.py | `grep -r "rbac\|RBAC" app/api/deps.py` | Uses core.rbac | ☐ |

---

## 10. Audit Logging

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 10.1 | AuditLogger class exists | `grep -r "class AuditLogger" app/core/audit_log.py` | Found | ☐ |
| 10.2 | 20+ event types defined | `grep -c "AUDIT_" app/core/audit_log.py | head -1` | > 20 | ☐ |
| 10.3 | Critical events flush immediately | `grep -r "_critical_events" app/core/audit_log.py` | Set defined | ☐ |
| 10.4 | Sanitization removes secrets | `pytest tests/test_security.py::TestAuditLogger::test_sanitize_values -xvs` | PASS | ☐ |
| 10.5 | Correlation ID support | `grep -r "correlation_id" app/core/audit_log.py` | ContextVar used | ☐ |
| 10.6 | Never logs passwords/tokens | `pytest tests/test_security.py::TestAuditLogger::test_sanitize_values -xvs` | PASS | ☐ |
| 10.7 | Convenience functions exist | `grep -r "async def log_" app/core/audit_log.py` | 8+ functions | ☐ |

---

## 11. Configuration Hardening

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 11.1 | SECURITY_CREDENTIAL_ENCRYPTION_KEY in config | `grep -r "credential_encryption_key" config.yaml .env.example` | Both files | ☐ |
| 11.2 | Production validation for encryption key | `grep -r "validate_credential_encryption_key" app/core/config.py` | Validator exists | ☐ |
| 11.3 | Debug defaults false in production | `grep -r "debug.*false" config.yaml` | Found | ☐ |
| 11.4 | CORS restricted origins | `grep -r "cors_origins" config.yaml` | Listed, not * | ☐ |
| 11.5 | Trusted hosts separate from CORS | `grep -r "APP_TRUSTED_HOSTS\|trusted_hosts" app/core/config.py app/main.py` | Separate setting | ☐ |
| 11.6 | Precedence: env > .env > YAML > defaults | `grep -r "settings_customise_sources" app/core/config.py` | Correct order | ☐ |

---

## 12. Mass Assignment Protection

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 12.1 | Separate Create/Update/Read schemas | `ls app/schemas/` | Multiple schema files | ☐ |
| 12.2 | tenant_id not in create schemas | `grep -r "tenant_id" app/schemas/ --include="*.py" | grep -v "read\|response"` | Not in create | ☐ |
| 12.3 | role/is_superuser protected | `grep -r "role\|is_superuser" app/schemas/ --include="*.py" | grep -v "read\|response"` | Not in create/update | ☐ |
| 12.4 | created_by protected | `grep -r "created_by" app/schemas/ --include="*.py" | grep -v "read\|response"` | Not in create/update | ☐ |

---

## 13. Celery Tenant Isolation

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 13.1 | celery_tenant.py exists | `ls app/core/celery_tenant.py` | Exists | ☐ |
| 13.2 | tenant_db_context used | `grep -r "tenant_db_context" app/core/celery_tenant.py` | Found | ☐ |
| 13.3 | create_tenant_task decorator | `grep -r "create_tenant_task" app/core/celery_tenant.py` | Found | ☐ |
| 13.4 | Tasks require explicit tenant_id | `grep -r "tenant_id.*str" app/workers/tasks/*.py | head -5` | All have it | ☐ |
| 13.5 | Workers use credential encryption | `grep -r "credential_encryption" app/workers/tasks/*.py` | Used | ☐ |
| 13.6 | Celery task registration works | `pytest tests/test_security.py -k celery -xvs` | PASS | ☐ |

---

## 14. Campaign Safety

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 14.1 | Recipient tenant validation | `grep -r "tenant_id.*contact" app/workers/tasks/campaign_tasks_v2.py` | Validated | ☐ |
| 14.2 | Suppression list checking | `grep -r "suppression" app/workers/tasks/campaign_tasks_v2.py` | Checked | ☐ |
| 14.3 | Idempotency keys on sends | `grep -r "idempotency_key" app/models/__init__.py` | Column exists | ☐ |
| 14.4 | Bounded batching | `grep -r "batch_size" app/core/config.py` | Configurable | ☐ |

---

## 15. Security Test Suite

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 15.1 | test_security.py exists | `ls tests/test_security.py` | Exists | ☐ |
| 15.2 | All security tests pass | `pytest tests/test_security.py -q` | All PASS | ☐ |
| 15.3 | Original 21 tests still pass | `pytest tests/ -q --ignore=tests/test_security.py` | 21 PASS | ☐ |
| 15.4 | Combined test suite passes | `pytest tests/ -q` | All PASS | ☐ |

---

## 16. Security Scans

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 16.1 | pip-audit runs | `pip-audit --desc` | No Critical | ☐ |
| 16.2 | bandit runs | `bandit -r app/` | No High (or justified) | ☐ |
| 16.3 | detect-secrets runs | `detect-secrets scan` | Baseline generated | ☐ |
| 16.4 | ruff passes | `ruff check app/ tests/` | No errors | ☐ |
| 16.5 | ruff format passes | `ruff format --check app/ tests/` | Clean | ☐ |

---

## 17. Production Docker

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 17.1 | Multi-stage Dockerfile | `grep -c "FROM.*AS" Dockerfile` | ≥ 2 stages | ☐ |
| 17.2 | Non-root user | `grep -r "USER " Dockerfile` | Not root | ☐ |
| 17.3 | No dev deps in final image | `grep -r "pytest\|bandit\|ruff" Dockerfile` | Not in final stage | ☐ |
| 17.4 | Healthcheck configured | `grep -r "HEALTHCHECK" Dockerfile` | Exists | ☐ |
| 17.5 | docker-compose.prod.yml exists | `ls docker-compose.prod.yml` | Exists | ☐ |
| 17.6 | PostgreSQL not exposed in prod | `grep -A5 "postgres:" docker-compose.prod.yml | grep ports` | No ports | ☐ |
| 17.7 | Redis not exposed in prod | `grep -A5 "redis:" docker-compose.prod.yml | grep ports` | No ports | ☐ |
| 17.8 | Internal networks defined | `grep -r "networks:" docker-compose.prod.yml` | Exists | ☐ |
| 17.9 | No demo passwords in prod | `grep -r "postgres" docker-compose.prod.yml` | No plaintext | ☐ |

---

## 18. GitHub Actions Gate 2 Pipeline

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 18.1 | Workflow file exists | `ls .github/workflows/checkpoint-2.yml` | Exists | ☐ |
| 18.2 | Triggers on checkpoint-2 branch | `grep -r "checkpoint-2-security-hardening" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.3 | PostgreSQL 16 service | `grep -r "postgres:16" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.4 | Redis 7 service | `grep -r "redis:7" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.5 | Compile step | `grep -r "compileall" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.6 | Mapper step | `grep -r "configure_mappers" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.7 | Alembic empty DB step | `grep -r "alembic upgrade head" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.8 | RLS catalog verification | `grep -r "pg_policies\|pg_tables" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.9 | No duplicate policies check | `grep -r "DUPLICATE POLICIES" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.10 | Celery task registration | `grep -r "celery_app.tasks" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.11 | Full pytest step | `grep -r "pytest.*-q" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.12 | Security tests step | `grep -r "test_security.py" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.13 | pip-audit step | `grep -r "pip-audit" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.14 | bandit step | `grep -r "bandit" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.15 | detect-secrets step | `grep -r "detect-secrets" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.16 | ruff step | `grep -r "ruff" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.17 | Production Docker build | `grep -r "docker build" .github/workflows/checkpoint-2.yml` | Found | ☐ |
| 18.18 | Production compose check | `grep -r "docker-compose.prod" .github/workflows/checkpoint-2.yml` | Found | ☐ |

---

## 19. Final Verification

| # | Check | Command | Expected Result | Status |
|---|-------|---------|-----------------|--------|
| 19.1 | All above items PASS | Review checklist | All ☑️ | ☐ |
| 19.2 | GitHub Actions GREEN | Check Actions tab | All jobs success | ☐ |
| 19.3 | Final commit SHA recorded | `git rev-parse HEAD` | Recorded | ☐ |
| 19.4 | Branch descends from 1D | `git log --oneline --ancestry-path 725acda..HEAD` | Shows 1D as ancestor | ☐ |

---

## Final Status

### Gate 2: COMPLETE ✅

**All items verified with actual command execution.**

### Gate 2: NOT COMPLETE ❌

**Blocking items:**
- [ ] Item X: Description
- [ ] Item Y: Description

---

**Verified by**: _______________  
**Date**: _______________  
**Git SHA**: _______________  
**GitHub Actions Run ID**: _______________