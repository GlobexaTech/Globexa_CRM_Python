from sqlalchemy import select, func
from app.models import (
    Lead,
    Deal,
    Stage,
    Task,
    CampaignRecipient,
    AIUsageLog,
    AnalyticsEvent,
    OperationJob,
    Activity,
    AIInsight,
    Message,
)
from app.core.rbac import get_role_permissions
from app.services.crm.common import authorize, now


async def analytics(db, tenant_id, actor_id, view, start=None, end=None):
    member = await authorize(db, tenant_id, actor_id, "analytics:read")
    permissions = get_role_permissions(member.role)
    required = {
        "pipeline": ("deals:read",),
        "conversion": ("leads:read",),
        "campaigns": ("campaigns:analytics",),
        "activity": ("tasks:read", "conversations:read"),
        "ai": ("ai:chat",),
        "dashboard": ("leads:read", "deals:read", "tasks:read"),
    }
    for permission in required[view]:
        await authorize(db, tenant_id, actor_id, permission)

    def dated(query, model):
        if start:
            query = query.where(model.created_at >= start)
        if end:
            query = query.where(model.created_at < end)
        return query

    async def count(model, *conditions):
        query = (
            select(func.count())
            .select_from(model)
            .where(model.tenant_id == tenant_id, *conditions)
        )
        if start:
            query = query.where(model.created_at >= start)
        if end:
            query = query.where(model.created_at < end)
        return await db.scalar(query)

    if view == "pipeline":
        rows = (
            await db.execute(
                dated(
                    select(
                        Stage.id,
                        Stage.name,
                        func.count(Deal.id),
                        func.coalesce(func.sum(Deal.value), 0),
                        Deal.currency,
                    )
                    .join(
                        Deal,
                        (Deal.stage_id == Stage.id) & (Deal.tenant_id == tenant_id),
                        isouter=True,
                    )
                    .where(Stage.tenant_id == tenant_id),
                    Deal,
                )
                .group_by(Stage.id, Stage.name, Deal.currency)
                .order_by(Stage.id)
            )
        ).all()
        return {
            "stages": [
                {
                    "id": r[0],
                    "name": r[1],
                    "deals": r[2],
                    "value": r[3],
                    "currency": r[4],
                }
                for r in rows
            ],
            "value_unit": "stored_currency_minor_units",
        }
    if view == "ai":
        rows = (
            await db.execute(
                dated(
                    select(
                        AIUsageLog.success,
                        func.count(),
                        func.sum(AIUsageLog.total_tokens),
                        func.sum(AIUsageLog.estimated_cost_usd),
                        func.count().filter(AIUsageLog.estimated_cost_usd.is_(None)),
                    ).where(AIUsageLog.tenant_id == tenant_id),
                    AIUsageLog,
                ).group_by(AIUsageLog.success)
            )
        ).all()
        return {
            "usage": [
                {
                    "success": r[0],
                    "requests": r[1],
                    "tokens": r[2],
                    "known_cost_usd": r[3],
                    "unpriced_requests": r[4],
                }
                for r in rows
            ]
        }
    if view == "campaigns":
        rows = (
            await db.execute(
                dated(
                    select(CampaignRecipient.status, func.count()).where(
                        CampaignRecipient.tenant_id == tenant_id
                    ),
                    CampaignRecipient,
                ).group_by(CampaignRecipient.status)
            )
        ).all()
        return {"delivery_status": {r[0].value: r[1] for r in rows}}
    if view == "conversion":
        total = await count(Lead)
        converted = await count(Lead, Lead.converted_at.is_not(None))
        return {
            "leads": total,
            "converted": converted,
            "conversion_rate": converted / total if total else 0,
        }
    if view == "activity":
        query = select(AnalyticsEvent.event_type, func.count()).where(
            AnalyticsEvent.tenant_id == tenant_id
        )
        if start:
            query = query.where(AnalyticsEvent.created_at >= start)
        if end:
            query = query.where(AnalyticsEvent.created_at < end)
        rows = (await db.execute(query.group_by(AnalyticsEvent.event_type))).all()
        inbound = (
            select(
                Message.conversation_id,
                func.min(Message.occurred_at).label("first_received"),
            )
            .where(Message.tenant_id == tenant_id, Message.direction == "inbound")
            .group_by(Message.conversation_id)
            .subquery()
        )
        next_reply = (
            select(func.min(Message.occurred_at))
            .where(
                Message.tenant_id == tenant_id,
                Message.direction == "outbound",
                Message.status.in_(["sent", "delivered"]),
                Message.conversation_id == inbound.c.conversation_id,
                Message.occurred_at >= inbound.c.first_received,
            )
            .correlate(inbound)
            .scalar_subquery()
        )
        intervals = select(
            func.extract("epoch", next_reply - inbound.c.first_received).label(
                "seconds"
            )
        ).subquery()
        response = (
            await db.execute(
                select(func.avg(intervals.c.seconds), func.count(intervals.c.seconds))
            )
        ).one()
        return {
            "events": dict(rows),
            "source": "processed_domain_events",
            "first_response_seconds": response[0],
            "response_sample_count": response[1],
            "response_window": "all_time",
        }
    result = {
        "leads": await count(Lead),
        "deals": await count(Deal),
        "open_tasks": await count(Task, Task.completed_at.is_(None)),
        "completed_tasks": await count(Task, Task.completed_at.is_not(None)),
        "generated_at": now(),
        "pending_jobs": await count(
            OperationJob, OperationJob.status.in_(["pending", "retry"])
        ),
        "failed_jobs": await count(
            OperationJob, OperationJob.status.in_(["failed", "unknown"])
        ),
    }
    from app.services.crm.customer import summary

    if "tasks:read" in permissions:
        tasks = (
            await db.scalars(
                select(Task)
                .where(Task.tenant_id == tenant_id, Task.completed_at.is_(None))
                .order_by(Task.due_date.asc().nullslast())
                .limit(10)
            )
        ).all()
        activities = (
            await db.scalars(
                select(Activity)
                .where(Activity.tenant_id == tenant_id)
                .order_by(Activity.created_at.desc())
                .limit(10)
            )
        ).all()
        result.update(
            tasks=[summary(r) for r in tasks],
            activities=[summary(r) for r in activities],
        )
    if "ai:chat" in permissions:
        insights = (
            await db.scalars(
                select(AIInsight)
                .where(AIInsight.tenant_id == tenant_id)
                .order_by(AIInsight.created_at.desc())
                .limit(10)
            )
        ).all()
        result["ai_insights"] = [summary(r) for r in insights]
    result["pipeline"] = (
        await analytics(db, tenant_id, actor_id, "pipeline", start, end)
    )["stages"]
    return result
