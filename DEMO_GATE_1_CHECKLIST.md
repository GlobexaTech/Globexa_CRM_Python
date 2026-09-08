# DEMO_GATE_1_CHECKLIST.md

## Globexa CRM — Demo Gate 1: Backend Stabilization Checklist

**Status**: ✅ **17/17 checks PASS**

---

| Check | Status | Evidence |
|-------|--------|----------|
| **Python compile** | ✅ PASS | Checkpoint 1D CI compiles `app`, `alembic`, and `demo.py` with 0 errors |
| **SQLAlchemy mapping** | ✅ PASS | `configure_mappers()` succeeds — `MAPPERS_OK` |
| **PostgreSQL** | ✅ PASS | Fresh PostgreSQL 16 service healthy; migrations and integration tests succeed |
| **Redis** | ✅ PASS | Fresh Redis 7 service healthy; Celery configuration/registration succeeds |
| **Alembic** | ✅ PASS | Empty database migrates `001` → `006_add_missing_enum_labels (head)` |
| **FastAPI startup** | ✅ PASS | Application imports and API integration tests execute successfully |
| **Celery startup** | ✅ PASS | Required V2 campaign/integration task modules load — `CELERY_TASKS_OK` |
| **Authentication route** | ✅ PASS | Auth integration tests: 8/8 pass |
| **Tenant validation** | ✅ PASS | JWT tenant, `X-Tenant-ID`, tenant path, and membership context are enforced before protected route execution; isolation tests pass |
| **Contacts route** | ✅ PASS | CRUD + list routes present |
| **Companies route** | ✅ PASS | CRUD + list routes present |
| **Leads route** | ✅ PASS | CRUD + list + search routes present |
| **Deals route** | ✅ PASS | CRUD + pipeline-management routes present |
| **Tasks route** | ✅ PASS | CRUD + list + overdue-filter routes present |
| **Notes route** | ✅ PASS | CRUD + list + filtering routes present |
| **Activities route** | ✅ PASS | Activity listing/filtering route present |
| **Swagger docs** | ✅ PASS | `/docs`, `/redoc`, and OpenAPI routes remain enabled |

---

## Checkpoint 1D Executable Verification

GitHub Actions workflow: `.github/workflows/checkpoint-1d.yml`

Verified successfully on run **33722246182** after the Checkpoint 1D test-isolation and dependency repairs:

```text
PostgreSQL 16:                  HEALTHY
Redis 7:                       HEALTHY
Python compile:                PASS
SQLAlchemy mapper config:      MAPPERS_OK
Alembic:                       006_add_missing_enum_labels (head)
Celery V2 task registration:   CELERY_TASKS_OK
Pytest:                        21 passed, 1 warning
```

Test breakdown:

```text
tests/test_auth.py              8 passed
tests/test_config.py            4 passed
tests/test_health.py            4 passed
tests/test_tenant_isolation.py  5 passed
TOTAL                           21 passed
```

The single pytest warning is Passlib's use of Python's deprecated standard-library `crypt` module; it does not affect the Gate 1 pass result.

---

## Tenant Validation — Previous Limitation Closed

The earlier 16/17 checklist documented that tenant middleware ran before `user_tenant_id` was available and therefore could not make `X-Tenant-ID` authoritative.

Checkpoint 1D closes that limitation by validating tenant context directly in middleware before protected route execution:

- resolved/header tenant must match the JWT access-token tenant,
- tenant IDs embedded in `/api/v1/tenants/{tenant_id}` paths must match the active tenant,
- authenticated users must have membership in the selected tenant, and
- cross-tenant attempts return HTTP 403.

Automated tenant-isolation tests verify both mismatched headers and cross-tenant path access.

---

## Explicit Gate 2 Scope

The following remain intentionally deferred security-hardening work and are **not** Gate 1 failures:

- PostgreSQL Row-Level Security (RLS) policies.
- Provider-specific webhook HMAC/signature hardening.

---

**Gate 1 Status: COMPLETE ✅ — 17/17 PASS**

See `CHECKPOINT_1D_REPORT.md` for the complete repair and verification record.
