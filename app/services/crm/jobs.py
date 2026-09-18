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
    "provider_webhook": "integrations:webhooks",
    "workforce": "ai:chat",
    "workforce_approval": "ai:chat",
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
        if job.kind in {"campaign_send", "message_send", "ai", "workforce"}:
            job.status, job.error_code = "unknown", "worker_lost_after_external_claim"
            if job.kind == "workforce":
                from app.models import AgentExecution
                execution = await owned(db, AgentExecution, tenant_id, UUID(job.payload["execution_id"]))
                execution.state, execution.error_message, execution.failed_at = "failed", "worker_lost_after_external_claim", now()
            if job.kind == "message_send":
                message = await db.scalar(select(Message).where(Message.tenant_id == tenant_id,
                    Message.idempotency_key == "job:" + str(job.id)))
                if message:
                    message.status = "unknown"
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
        if job.kind == "message_send" and getattr(adapter, "name", None) == "whatsapp":
            from app.services.crm.conversations import validate_whatsapp_send
            conversation = await owned(db, Conversation, tenant_id, UUID(job.payload["conversation_id"]))
            await validate_whatsapp_send(db, tenant_id, conversation, job.payload["recipient"])
        job.attempts += 1
        if job.kind in {"sync", "campaign_send"} and not job.result.get("metered"):
            await meter(
                db,
                tenant_id,
                job.actor_id,
                "integrations" if job.kind == "sync" else "messages",
            )
            job.result = {"metered": True}
        if job.kind == "sync" and (job.result or {}).get("sync_job_id"):
            from app.models import SyncJob
            sync = await owned(db, SyncJob, tenant_id, UUID(job.result["sync_job_id"]))
            if sync.status == "cancelled":
                job.status = "cancelled"
                await db.commit()
                return job
        if integration:
            token = await access_token(db, tenant_id, integration)
        if job.kind == "message_send" and job.payload.get("approval_id"):
            from app.services.ai.approval import validate_approved_send
            await validate_approved_send(db, job, integration)
        job.status, job.claimed_at = "running", now()
        if job.kind == "message_send":
            message = await db.scalar(select(Message).where(Message.tenant_id == tenant_id,
                                     Message.idempotency_key == "job:" + str(job.id)))
            if message:
                message.status = "sending"
        # Persist the claim before crossing an external boundary. Crashes cannot silently resend.
        if job.kind != "automation":
            await db.commit()
        if job.kind == "workforce":
            from app.services.ai.agent import run_execution
            result = await run_execution(db, job, gateway=gateway)
            job.result = result
            job.status = "retry" if result.get("pending") else "completed"
            job.available_at = now() + timedelta(seconds=5)
            job.completed_at = None if result.get("pending") else now()
            await db.commit()
            return job
        async with db.begin_nested():
            if job.kind in {"campaign_send", "message_send"}:
                if job.kind == "message_send":
                    # The durable claim committed above released locks. Recheck the
                    # real write boundary, including changes during token refresh.
                    await db.refresh(job, with_for_update=True)
                    integration = await db.scalar(select(Integration).where(
                        Integration.tenant_id == tenant_id,
                        Integration.id == UUID(job.payload["integration_id"])
                    ).with_for_update().execution_options(populate_existing=True))
                    if not integration:
                        raise ProviderFailure("integration_disconnected")
                    adapter = adapter_for(integration)
                    token = await access_token(db, tenant_id, integration)
                    await authorize(db, tenant_id, job.actor_id, "conversations:send")
                    if await suppressed(db, tenant_id, job.payload["recipient"]):
                        raise ProviderFailure("recipient_suppressed")
                    if getattr(adapter, "name", None) == "whatsapp":
                        from app.services.crm.conversations import validate_whatsapp_send
                        conversation = await owned(db, Conversation, tenant_id, UUID(job.payload["conversation_id"]), True)
                        await validate_whatsapp_send(db, tenant_id, conversation, job.payload["recipient"])
                    if job.payload.get("approval_id"):
                        from app.services.ai.approval import validate_approved_send
                        await validate_approved_send(db, job, integration)
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
                from app.services.crm.provider_pipeline import execute_sync_page
                result = await execute_sync_page(db, tenant_id, job, integration, adapter, token)
            elif job.kind == "provider_webhook":
                from app.services.crm.provider_pipeline import process_receipt
                result = await process_receipt(db, tenant_id, UUID(job.payload["receipt_id"]))
            elif job.kind == "workforce_approval":
                from app.services.ai.approval import run_approval
                result = await run_approval(db, job)
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
            if result.get("has_more") or result.get("pending") or result.get("state") == "failed":
                job.status, job.completed_at = "retry", None
                job.available_at = now() + timedelta(seconds=5)
            if result.get("has_more"):
                job.attempts = 0  # Retry budget is per successfully persisted page.
            if result.get("cancelled"):
                job.status = "cancelled"
            if result.get("state") == "dead_letter":
                job.status, job.error_code = "failed", "webhook_dead_letter"
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
        job.available_at = now() + timedelta(seconds=max(getattr(exc, "retry_after", 60), 60 * max(1, job.attempts)))
        audit(
            db,
            tenant_id,
            job.actor_id,
            job.kind + ".failed",
            "operation_job",
            job.id,
            False,
        )
        if job.kind == "workforce":
            from app.models import AgentExecution
            execution = await owned(db, AgentExecution, tenant_id, UUID(job.payload["execution_id"]))
            execution.state, execution.error_message, execution.failed_at = "failed", code, now()
        if job.kind == "workforce_approval":
            from app.models import ApprovalRequest
            approval = await owned(db, ApprovalRequest, tenant_id, UUID(job.payload["approval_id"]), True)
            if approval.status == "approved":
                approval.status = "failed"
                approval.execution_result = {"error": code}
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
            from app.models import SyncJob
            sync_id = (job.result or {}).get("sync_job_id")
            if sync_id:
                sync = await owned(db, SyncJob, tenant_id, UUID(sync_id))
                sync.status, sync.error_message = "partial" if job.status == "retry" else "failed", code
            if integration:
                integration.last_sync_error = code
                integration.last_sync_status = SyncStatusEnum.FAILED
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
