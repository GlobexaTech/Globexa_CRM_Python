"""Boundary checks for JSON ingress and the legacy computed-index search API."""

import pytest
from tests.test_checkpoint3 import crm  # noqa: F401
from app.services.search.foundation import PostgresFTSBackend
from tests.test_rls import isolated_rls  # noqa: F401


async def test_request_size_is_enforced_before_auth_or_json_parsing(client):
    response = await client.post(
        "/api/v1/auth/login", content=b"x" * 1_048_577, headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}


async def test_chunked_body_cannot_bypass_limit(client):
    async def chunks():
        for _ in range(3):
            yield b"x" * 524288

    response = await client.post(
        "/api/v1/auth/login", content=chunks(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


async def test_computed_fts_parameters_filters_and_tenant_scope(db_session, crm):
    backend = PostgresFTSBackend(db_session)
    own = await backend.search("contact", "Alice", crm["tenant"])
    assert [row["id"] for row in own] == [crm["contact"].id]
    assert await backend.search("contact", "'; DROP TABLE contacts; --", crm["tenant"]) == []
    assert (
        await backend.search("contact", "Alice", crm["tenant"], {"first_name": "' OR 1=1 --"}) == []
    )
    with pytest.raises(ValueError):
        await backend.search("contacts; DROP TABLE contacts", "Alice", crm["tenant"])
    with pytest.raises(ValueError):
        await backend.search("contact", "Alice", crm["tenant"], {"tenant_id": str(crm["tenant"])})
    await backend.index("contact", crm["contact"].id, {}, crm["tenant"])
    with pytest.raises(NotImplementedError):
        await backend.remove("contact", crm["contact"].id, crm["tenant"])
    assert [row["id"] for row in await backend.search("contact", "Alice", crm["tenant"])] == [
        crm["contact"].id
    ]


async def test_actual_usage_worker_aggregates_only_its_tenant_without_double_counting(
    isolated_rls, monkeypatch
):
    import asyncio
    import os
    from datetime import timedelta
    from sqlalchemy import select, func
    from app.core.config import get_settings
    from app.core.tenant_context import tenant_context
    from app.models import UsageRecord
    from app.services.crm.common import now
    from app.workers.tasks.usage_tasks import aggregate_daily_usage, cleanup_old_audit_logs

    factory, tenants, users, _, _ = isolated_rls
    for index in range(2):
        with tenant_context(tenants[index], users[index]):
            async with factory() as db:
                db.add(
                    UsageRecord(
                        tenant_id=tenants[index],
                        user_id=users[index],
                        metric="messages",
                        quantity=7 + index * 6,
                        period_start=now(),
                        period_end=now() + timedelta(days=1),
                    )
                )
                await db.commit()
    monkeypatch.setattr(
        get_settings().database,
        "username",
        os.environ.get("RUNTIME_DATABASE_ROLE", "globexa_runtime"),
    )
    monkeypatch.setattr(
        get_settings().database, "password", os.environ["RUNTIME_DATABASE_PASSWORD"]
    )
    for _ in range(2):
        result = await asyncio.to_thread(aggregate_daily_usage.run, str(tenants[0]))
        assert result["totals"] == {"messages": 7}
    with tenant_context(tenants[0], users[0]):
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(UsageRecord)) == 1
    with pytest.raises(ValueError, match="approved administrator"):
        cleanup_old_audit_logs.run(str(tenants[0]))
