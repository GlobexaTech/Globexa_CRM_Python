"""Set and restore AI quota only in the isolated Checkpoint 4 browser fixture.

This is a test process helper, not an HTTP endpoint or production admin API.
It uses the real restricted runtime role and tenant context. stdout contains only
the previous quota settings so the browser test can restore them in finally.
"""
import argparse
import asyncio
import json
from uuid import UUID

from checkpoint4_runtime import ROOT, load_environment


async def change_quota(state):
    from sqlalchemy import select
    from app.core.tenant_context import tenant_db_context
    from app.models import FeatureEntitlement

    fixture = json.loads((ROOT / "evidence" / "fixture.json").read_text(encoding="utf-8"))
    tenant_id = UUID(fixture["tenantA"])
    actor_id = UUID(fixture["users"]["owner"]["id"])
    async with tenant_db_context(tenant_id, actor_id) as db:
        row = await db.scalar(select(FeatureEntitlement).where(
            FeatureEntitlement.tenant_id == tenant_id,
            FeatureEntitlement.feature_key == "ai_credits",
        ).with_for_update())
        if row is None:
            raise RuntimeError("AI fixture entitlement is missing")
        previous = {"enabled": row.enabled, "limit": row.limit_value}
        row.enabled, row.limit_value = state["enabled"], state["limit"]
    return previous


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("state", help="Exact JSON object containing enabled and limit")
    args = parser.parse_args()
    load_environment()  # requires APP_ENVIRONMENT=testing and globexa_cp4 database
    state = json.loads(args.state)
    if set(state) != {"enabled", "limit"} or type(state["enabled"]) is not bool:
        raise ValueError("Invalid fixture entitlement state")
    if state["limit"] is not None and (type(state["limit"]) is not int or not -1 <= state["limit"] <= 1_000_000_000):
        raise ValueError("Invalid fixture quota")
    print(json.dumps(asyncio.run(change_quota(state))))


if __name__ == "__main__":
    main()
