"""Durable operation execution with explicit handling of uncertain external effects."""

from datetime import timedelta
from uuid import UUID
from sqlalchemy import select
from fastapi import HTTPException
from app.models import (
    OperationJob,
    Integration,
    IntegrationSyncLog,
    SyncStatusEnum,
    Message,
    Campaign,
    CampaignRecipient,
    CampaignRecipientStatusEnum,
    Contact,
    ExecutionLog,
    Conversation,
)
from app.services.crm.common import owned, authorize, audit, now, meter
from app.services.crm.providers import adapter_for, ProviderFailure
from app.services.crm.integrations import access_token
from app.services.crm.conversations import suppressed, ingest_message
from app.services.crm.campaigns import update_stats

JOB_PERMISSIONS = {
    "campaign_send": "campaigns:send",
    "message_send": "conversations:send",
    "sync": "integrations:write",
    "ai": "ai:chat",
    "automation": "automation:write",
}


async def execute_job(db, tenant_id, job_id, *, gateway=None):
    job = await db.scalar(
        select(OperationJob)
        .where(OperationJob.tenant_id == tenant_id, OperationJob.id == job_id)
        .with_for_update(skip_locked=True)
    )
    if not job or job.status in {
        "completed",
        "failed",
        "unknown",
        "awaiting_approval",
        "cancelled",
    }:
        return
    if job.available_at > now():
        return
    if job.status == "running":
        if job.claimed_at and job.claimed_at > now() - timedelta(minutes=5):
            return
        if job.kind in {"campaign_send", "message_send", "ai"}:
            job.status, job.error_code = "unknown", "worker_lost_after_external_claim"
            await db.commit()
            return
    if job.kind not in JOB_PERMISSIONS:
        job.status, job.error_code = "failed", "unsupported_job"
        return
    from app.core.tenant_context import bind_context

    await bind_context(db, tenant_id, job.actor_id)
    integration, token, adapter = None, None, None
    try:
        await authorize(db, tenant_id, job.actor_id, JOB_PERMISSIONS[job.kind])
        if job.kind in {"campaign_send", "message_send", "sync"}:
            integration = await owned(
                db, Integration, tenant_id, UUID(job.payload["integration_id"])
            )
            adapter = adapter_for(integration)
        if job.kind == "campaign_send":
            campaign = await owned(
                db, Campaign, tenant_id, UUID(job.payload["campaign_id"])
            )
            if campaign.status.value == "paused":
                return
            if campaign.status.value != "sending":
                job.status = "cancelled"
                return
            recipient = await owned(
                db, CampaignRecipient, tenant_id, UUID(job.payload["recipient_id"])
            )
            contact = await owned(db, Contact, tenant_id, recipient.contact_id)
            earlier = (
                await db.scalars(
                    select(CampaignRecipient).where(
                        CampaignRecipient.tenant_id == tenant_id,
                        CampaignRecipient.campaign_id == campaign.id,
                        CampaignRecipient.contact_id == contact.id,
                        CampaignRecipient.created_at <= recipient.created_at,
                        CampaignRecipient.id != recipient.id,
                    )
                )
            ).all()
            # Replies/opt-outs stop all remaining sequence steps.
            blocked = await suppressed(db, tenant_id, recipient.email, contact) or any(
                r.replied_at or r.bounced_at or r.unsubscribed_at for r in earlier
            )
            if not blocked and job.payload["step"] > 0:
                previous = await db.scalar(
                    select(OperationJob).where(
                        OperationJob.tenant_id == tenant_id,
                        OperationJob.kind == "campaign_send",
                        OperationJob.payload["campaign_id"].astext == str(campaign.id),
                        OperationJob.payload["recipient"].astext == recipient.email,
                        OperationJob.payload["step"].as_integer()
                        == job.payload["step"] - 1,
                    )
                )
                if previous and previous.status in {"failed", "unknown", "cancelled"}:
                    blocked = True
                elif previous and previous.status != "completed":
                    return
            if blocked:
                recipient.status = CampaignRecipientStatusEnum.SUPPRESSED
                job.status, job.result = "completed", {"suppressed": True}
                await update_stats(db, tenant_id, campaign.id)
                return
        elif job.kind == "message_send" and await suppressed(
            db, tenant_id, job.payload["recipient"]
        ):
            raise ProviderFailure("recipient_suppressed")
        job.attempts += 1
        if job.kind in {"sync", "campaign_send"} and not job.result.get("metered"):
            await meter(
                db,
                tenant_id,
                job.actor_id,
                "integrations" if job.kind == "sync" else "messages",
            )
            job.result = {"metered": True}
        if integration:
            token = await access_token(db, tenant_id, integration)
        job.status, job.claimed_at = "running", now()
        # Persist the claim before crossing an external boundary. Crashes cannot silently resend.
        if job.kind != "automation":
            await db.commit()
        async with db.begin_nested():
            if job.kind in {"campaign_send", "message_send"}:
                result = await adapter.send(token, job.payload, str(job.id))
                if job.kind == "campaign_send":
                    recipient = await owned(
                        db,
                        CampaignRecipient,
                        tenant_id,
                        UUID(job.payload["recipient_id"]),
                    )
                    recipient.status, recipient.sent_at = (
                        CampaignRecipientStatusEnum.SENT,
                        now(),
                    )
                    recipient.provider_message_id = result.get("provider_message_id")
                    conversation = Conversation(
                        tenant_id=tenant_id,
                        contact_id=recipient.contact_id,
                        company_id=contact.company_id,
                        integration_id=integration.id,
                        subject=job.payload["subject"],
                        provider_thread_id=result.get("thread_id"),
                        last_message_at=now(),
                    )
                    db.add(conversation)
                    await db.flush()
                    db.add(
                        Message(
                            tenant_id=tenant_id,
                            conversation_id=conversation.id,
                            body=job.payload["body"],
                            direction="outbound",
                            status="sent",
                            recipient=recipient.email,
                            provider_message_id=result.get("provider_message_id"),
                            idempotency_key="job:" + str(job.id),
                        )
                    )
                else:
                    message = await db.scalar(
                        select(Message).where(
                            Message.tenant_id == tenant_id,
                            Message.idempotency_key == "job:" + str(job.id),
                        )
                    )
                    message.status, message.provider_message_id, message.occurred_at = (
                        "sent",
                        result.get("provider_message_id"),
                        now(),
                    )
            elif job.kind == "sync":
                result = await adapter.sync(token, job.payload.get("cursor"))
                count = 0
                for item in result.get("messages", [])[:25]:
                    await ingest_message(db, tenant_id, integration, item)
                    count += 1
                log = IntegrationSyncLog(
                    tenant_id=tenant_id,
                    integration_id=integration.id,
                    sync_type="inbox",
                    status=SyncStatusEnum.COMPLETED,
                    records_processed=count,
                    started_at=job.claimed_at,
                    completed_at=now(),
                )
                db.add(log)
                integration.last_sync_at, integration.last_sync_status = (
                    now(),
                    SyncStatusEnum.COMPLETED,
                )
                integration.records_synced += count
                result = {"records_processed": count, "cursor": result.get("cursor")}
            elif job.kind == "automation":
                from app.services.crm.automation import execute_workflow

                result = await execute_workflow(db, tenant_id, job)
            else:
                from app.services.crm.ai import execute_ai

                result = await execute_ai(db, tenant_id, job, gateway)
            job.status, job.result, job.error_code, job.completed_at = (
                "completed",
                result,
                None,
                now(),
            )
            audit(
                db,
                tenant_id,
                job.actor_id,
                job.kind + ".completed",
                "operation_job",
                job.id,
            )
        if job.kind == "campaign_send":
            await update_stats(db, tenant_id, UUID(job.payload["campaign_id"]))
        await db.commit()
    except (
        ProviderFailure,
        HTTPException,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
    ) as exc:
        # Never persist exception text, request headers, provider bodies or credentials.
        code = exc.code if isinstance(exc, ProviderFailure) else type(exc).__name__
        uncertain = isinstance(exc, ProviderFailure) and exc.uncertain
        retryable = isinstance(exc, ProviderFailure) and exc.retryable
        job.status = (
            "unknown"
            if uncertain
            else "retry"
            if retryable and job.attempts < 3
            else "failed"
        )
        job.error_code = code
        job.available_at = now() + timedelta(seconds=60 * max(1, job.attempts))
        audit(
            db,
            tenant_id,
            job.actor_id,
            job.kind + ".failed",
            "operation_job",
            job.id,
            False,
        )
        if job.kind == "automation":
            log = await owned(
                db, ExecutionLog, tenant_id, UUID(job.payload["execution_id"])
            )
            log.status, log.error_code = "failed", code
            log.attempts += 1
        if job.kind == "campaign_send" and job.status == "failed":
            recipient = await owned(
                db, CampaignRecipient, tenant_id, UUID(job.payload["recipient_id"])
            )
            recipient.status, recipient.error_message = (
                CampaignRecipientStatusEnum.FAILED,
                code,
            )
            await update_stats(db, tenant_id, UUID(job.payload["campaign_id"]))
        if job.kind == "message_send":
            message = await db.scalar(
                select(Message).where(
                    Message.tenant_id == tenant_id,
                    Message.idempotency_key == "job:" + str(job.id),
                )
            )
            if message:
                message.status = (
                    "unknown"
                    if uncertain
                    else "failed"
                    if job.status == "failed"
                    else "queued"
                )
        if job.kind == "sync":
            db.add(
                IntegrationSyncLog(
                    tenant_id=tenant_id,
                    integration_id=UUID(job.payload["integration_id"]),
                    sync_type="inbox",
                    status=SyncStatusEnum.FAILED,
                    error_message=code,
                    started_at=now(),
                    completed_at=now(),
                )
            )
        await db.commit()
    return job
