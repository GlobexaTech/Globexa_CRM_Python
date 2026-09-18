"""Explainable recommendations and measurements from actual tenant CRM records."""
from datetime import timedelta
from uuid import UUID
from sqlalchemy import select, func, or_
from fastapi import HTTPException
from app.models import (Lead, Contact, Deal, Task, Activity, DomainEvent, Campaign,
    CampaignRecipient, Conversation, Message, Integration, AutomationExecution, AutomationStepExecution, AIUsageLog, ApprovalRequest)
from app.services.crm.common import authorize, owned, now


async def inspect_entity(db, tenant_id, actor_id, kind, entity_type, entity_id):
    if kind == "customer":
        from app.services.crm.customer import customer360
        return await customer360(db, tenant_id, actor_id, {"lead": "leads", "contact": "contacts"}.get(entity_type, "contacts"), entity_id, 30, 0)
    if kind == "lead" or (kind == "next_best_action" and entity_type == "lead"):
        await authorize(db, tenant_id, actor_id, "leads:read")
        row = await owned(db, Lead, tenant_id, entity_id)
        await authorize(db, tenant_id, actor_id, "tasks:read")
        activity = await db.scalar(select(func.count()).select_from(Activity).where(Activity.tenant_id == tenant_id, Activity.lead_id == row.id))
        tasks = await db.scalar(select(func.count()).select_from(Task).where(Task.tenant_id == tenant_id, Task.lead_id == row.id, Task.completed_at.is_(None)))
        score, reasons = 0, []
        for matched, points, reason in ((row.contact_id is not None, 20, "Linked contact"), (row.company_id is not None, 15, "Linked company"),
            (bool(row.description), 10, "Recorded requirement"), (activity > 0, 20, "Recorded activity"),
            (getattr(row.status, "value", row.status) in {"qualified", "converted"}, 35, "Qualified lead state")):
            if matched: score += points; reasons.append({"input": reason, "points": points})
        duplicates = []
        if row.contact_id:
            duplicates = [str(value) for value in (await db.scalars(select(Lead.id).where(Lead.tenant_id == tenant_id,
                Lead.contact_id == row.contact_id, Lead.id != row.id).limit(20))).all()]
        action = "review_duplicates" if duplicates else "follow_up" if tasks else "create_follow_up_task"
        return {"id": str(row.id), "score": score, "classification": "high" if score >= 70 else "medium" if score >= 40 else "low",
            "priority": "high" if score >= 70 else "normal", "reasons": reasons, "duplicate_ids": duplicates,
            "duplicate_basis": "same linked contact; review required", "ai_score": row.ai_score,
            "action": action, "reason": "Based on stored lead state, activity and open tasks", "confidence": None,
            "supporting_data": {"activity_count": activity, "open_tasks": tasks, "state": getattr(row.status, "value", row.status)},
            "enrichment": {"contact_id": str(row.contact_id) if row.contact_id else None, "company_id": str(row.company_id) if row.company_id else None, "provenance": "existing CRM relationships"}, "is_recommendation": True}
    if kind == "deal" or (kind == "next_best_action" and entity_type == "deal"):
        await authorize(db, tenant_id, actor_id, "deals:read")
        await authorize(db, tenant_id, actor_id, "tasks:read")
        row = await owned(db, Deal, tenant_id, entity_id)
        entered = await db.scalar(select(func.max(DomainEvent.created_at)).where(DomainEvent.tenant_id == tenant_id,
            DomainEvent.aggregate_id == str(row.id), DomainEvent.event_type == "deal.stage_changed"))
        entered = entered or row.created_at
        days = max(0, (now() - entered).total_seconds() / 86400)
        overdue = await db.scalar(select(func.count()).select_from(Task).where(Task.tenant_id == tenant_id, Task.deal_id == row.id,
            Task.completed_at.is_(None), Task.due_date < now()))
        risks = []
        if days >= 14: risks.append("No recorded stage change for at least 14 days")
        if overdue: risks.append("Overdue open tasks")
        if not row.owner_id: risks.append("No assigned owner")
        return {"id": str(row.id), "health": "at_risk" if risks else "on_track", "stalled": days >= 14, "stage_days": round(days, 2),
            "action": "review_stalled_deal" if days >= 14 else "complete_overdue_tasks" if overdue else "plan_next_contact",
            "reason": "; ".join(risks) if risks else "No configured risk rule matched", "confidence": None,
            "risk_indicators": risks, "supporting_data": {"stage_entered_at": entered.isoformat(), "overdue_tasks": overdue, "value": row.value}, "is_recommendation": True}
    if kind == "campaign":
        await authorize(db, tenant_id, actor_id, "campaigns:read")
        row = await owned(db, Campaign, tenant_id, entity_id)
        query = select(func.count()).select_from(CampaignRecipient).where(CampaignRecipient.tenant_id == tenant_id, CampaignRecipient.campaign_id == row.id)
        recipients = await db.scalar(query)
        sent = await db.scalar(query.where(CampaignRecipient.sent_at.is_not(None)))
        replied = await db.scalar(query.where(CampaignRecipient.replied_at.is_not(None)))
        opened = await db.scalar(query.where(CampaignRecipient.opened_at.is_not(None)))
        return {"id": str(row.id), "recipients": recipients, "sent": sent, "replied": replied, "opened": opened,
            "reply_rate": replied / sent if sent else None, "open_rate": opened / sent if sent else None,
            "conversion_rate": None, "conversion_limitation": "No verified campaign-to-deal conversion attribution", "provenance": "persisted provider recipient events"}
    raise HTTPException(422, "Unsupported intelligence resource")


async def analytics(db, tenant_id, actor_id, automation_id=None):
    await authorize(db, tenant_id, actor_id, "automation:read")
    await authorize(db, tenant_id, actor_id, "analytics:read")
    execution_filter = [AutomationExecution.tenant_id == tenant_id]
    if automation_id:
        from app.models import Automation
        await owned(db, Automation, tenant_id, automation_id)
        execution_filter.append(AutomationExecution.automation_id == automation_id)
    counts = (await db.execute(select(AutomationExecution.state, func.count()).where(*execution_filter).group_by(AutomationExecution.state))).all()
    values = {state: count for state, count in counts}; total = sum(values.values())
    terminal = sum(values.get(state, 0) for state in ("COMPLETED", "FAILED", "CANCELLED", "EXPIRED"))
    duration = await db.scalar(select(func.avg(func.extract("epoch", AutomationExecution.completed_at - AutomationExecution.started_at))).where(*execution_filter))
    execution_ids = select(AutomationExecution.id).where(*execution_filter)
    steps = AutomationStepExecution.execution_id.in_(execution_ids)
    step_duration = await db.scalar(select(func.avg(func.extract("epoch", AutomationStepExecution.completed_at - AutomationStepExecution.started_at))).where(AutomationStepExecution.tenant_id == tenant_id, steps))
    failures = (await db.execute(select(AutomationStepExecution.error_code, func.count()).where(AutomationStepExecution.tenant_id == tenant_id, steps,
        AutomationStepExecution.error_code.is_not(None)).group_by(AutomationStepExecution.error_code).order_by(func.count().desc()).limit(10))).all()
    usage = (await db.execute(select(func.count(), func.sum(AIUsageLog.total_tokens), func.sum(AIUsageLog.estimated_cost_usd),
        func.count().filter(AIUsageLog.total_tokens.is_(None))).where(AIUsageLog.tenant_id == tenant_id, AIUsageLog.automation_execution_id.in_(execution_ids)))).one()
    approvals = (await db.execute(select(ApprovalRequest.status, func.count()).where(ApprovalRequest.tenant_id == tenant_id,
        ApprovalRequest.automation_execution_id.in_(execution_ids)).group_by(ApprovalRequest.status))).all()
    approval_counts = dict(approvals); decided = sum(approval_counts.get(state, 0) for state in ("approved", "executed", "rejected", "failed"))
    provider_actions = await db.scalar(select(func.count()).select_from(AutomationStepExecution).where(AutomationStepExecution.tenant_id == tenant_id, steps,
        AutomationStepExecution.state == "COMPLETED", AutomationStepExecution.input["action"].astext.in_(["send_email", "send_whatsapp", "webhook_call"])))
    return {"executions": total, "states": values, "success_rate": values.get("COMPLETED", 0) / terminal if terminal else None,
        "failure_rate": values.get("FAILED", 0) / terminal if terminal else None, "average_duration_seconds": float(duration) if duration is not None else None,
        "average_step_duration_seconds": float(step_duration) if step_duration is not None else None, "top_failures": [{"code": code, "count": count} for code, count in failures],
        "ai_calls": usage[0], "measured_tokens": usage[1], "estimated_cost_usd": usage[2], "unknown_usage_calls": usage[3],
        "provider_actions": provider_actions, "approvals": approval_counts,
        "approval_rate": (approval_counts.get("approved", 0) + approval_counts.get("executed", 0)) / decided if decided else None,
        "conversion_rate": None, "conversion_limitation": "No verified conversion attribution is recorded"}
