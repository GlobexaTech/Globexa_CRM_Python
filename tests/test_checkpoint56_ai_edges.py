"""Additional workforce contracts against restricted PostgreSQL and transport doubles."""

import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import AgentExecution, Campaign, DomainEvent, Message, OperationJob
from app.schemas.workforce import ExecutionInput
from app.services.ai.agent import WorkforceSubscriber, run_execution
from app.services.ai.research import MAX_BYTES, fetch_public
from test_checkpoint6_workforce import ModelTransport, queue_run
from test_checkpoint6_workforce import workforce_db as workforce_db


@pytest.mark.parametrize(
    "event_type,entity_type,agent,tool",
    [
        ("lead.created", "lead", "research", "get_lead"),
        ("message.received", "conversation", "support", "get_conversation"),
        ("deal.stage_changed", "deal", "sales", "get_deal"),
        ("campaign.completed", "campaign", "analyst", "search_analytics"),
    ],
)
async def test_each_workforce_event_mapping_queues_scoped_idempotent_work(
    workforce_db, monkeypatch, event_type, entity_type, agent, tool
):
    db, tenant, actor, _, _, ids = workforce_db
    monkeypatch.setenv("WORKFORCE_EVENT_TRIGGERS", "true")
    if entity_type == "campaign":
        campaign = Campaign(
            tenant_id=tenant,
            name="Completed campaign analysis",
            type="broadcast",
            sender_name="Fixture",
            sender_email="sender@example.com",
            created_by_id=actor,
        )
        db.add(campaign)
        await db.flush()
        entity_id = campaign.id
    else:
        entity_id = ids[entity_type]
    aggregate_id = entity_id
    payload = {}
    if event_type == "message.received":
        message = await db.scalar(select(Message).where(Message.conversation_id == entity_id))
        aggregate_id = message.id
        payload = {"conversation_id": str(entity_id)}
    event = DomainEvent(
        tenant_id=tenant,
        actor_id=actor,
        event_type=event_type,
        aggregate_id=str(aggregate_id),
        payload=payload,
        idempotency_key=uuid4().hex,
    )
    db.add(event)
    await db.flush()
    subscriber = WorkforceSubscriber()
    await subscriber.handle(db, event)
    await subscriber.handle(db, event)
    await db.commit()
    executions = (
        await db.scalars(
            select(AgentExecution).where(AgentExecution.idempotency_key == "event:" + str(event.id))
        )
    ).all()
    assert len(executions) == 1
    execution = executions[0]
    assert (execution.agent_name, execution.actor_id, execution.tenant_id) == (agent, actor, tenant)
    assert execution.task["context"]["entity_type"] == entity_type
    assert execution.task["context"]["entity_id"] == str(entity_id)
    assert execution.task["tools"] == [tool] and execution.state == "queued"
    job = await db.get(OperationJob, execution.job_id)
    assert (job.kind, job.actor_id, job.tenant_id) == ("workforce", actor, tenant)
    assert job.payload["execution_id"] == str(execution.id)


@pytest.mark.parametrize(
    "recover", [True, False], ids=["recovers-after-safe-retry", "bounded-exhaustion"]
)
async def test_supervisor_retries_only_bounded_unavailable_children_and_summarizes_actual_states(
    workforce_db, monkeypatch, recover
):
    db, tenant, actor, _, _, ids = workforce_db
    monkeypatch.delenv("CRM_AI_PROVIDER", raising=False)
    model = ModelTransport(
        [
            {
                "summary": "Review the verified lead",
                "subtasks": [{"agent_name": "research", "objective": "Review verified lead facts"}],
            },
            {
                "summary": "The attempted work recovered."
                if recover
                else "All three attempts failed before a model call."
            },
        ]
    )
    gateway = model.gateway()
    child_gateway = None
    try:
        parent = await queue_run(
            db,
            tenant,
            actor,
            ExecutionInput(
                agent_name="supervisor",
                objective="Review the lead with bounded child work",
                context={"entity_type": "lead", "entity_id": ids["lead"]},
                tools=["get_lead"],
            ),
            gateway,
        )
        parent_id, parent_job_id = parent.id, parent.job_id
        initial = await db.scalar(
            select(AgentExecution).where(AgentExecution.parent_id == parent_id)
        )
        initial_id = initial.id
        await run_execution(db, await db.get(OperationJob, initial.job_id))
        first = await db.get(AgentExecution, initial_id)
        assert (
            first.state == "failed"
            and first.error_message == "model_unavailable"
            and not first.tools_used
        )
        # The parent creates one safe retry; repeated monitoring cannot enqueue duplicates.
        await run_execution(db, await db.get(OperationJob, parent_job_id), gateway)
        await run_execution(db, await db.get(OperationJob, parent_job_id), gateway)
        children = (
            await db.scalars(
                select(AgentExecution)
                .where(AgentExecution.parent_id == parent_id)
                .order_by(AgentExecution.attempts)
            )
        ).all()
        assert [child.attempts for child in children] == [0, 1]
        retry = children[-1]
        assert retry.task == first.task and retry.actor_id == actor and retry.tenant_id == tenant
        if recover:
            child_model = ModelTransport(
                [{"summary": "Verified lead context reviewed.", "actions": []}]
            )
            child_gateway = child_model.gateway()
            await run_execution(db, await db.get(OperationJob, retry.job_id), child_gateway)
            await run_execution(db, await db.get(OperationJob, parent_job_id), gateway)
            assert len(child_model.requests) == 1
        else:
            await run_execution(db, await db.get(OperationJob, retry.job_id))
            await run_execution(db, await db.get(OperationJob, parent_job_id), gateway)
            last = await db.scalar(
                select(AgentExecution).where(
                    AgentExecution.parent_id == parent_id, AgentExecution.attempts == 2
                )
            )
            assert last is not None
            await run_execution(db, await db.get(OperationJob, last.job_id))
            await run_execution(db, await db.get(OperationJob, parent_job_id), gateway)
        parent = await db.get(AgentExecution, parent_id)
        assert parent.state == "completed"
        children = (
            await db.scalars(
                select(AgentExecution)
                .where(AgentExecution.parent_id == parent_id)
                .order_by(AgentExecution.attempts)
            )
        ).all()
        assert [child.attempts for child in children] == ([0, 1] if recover else [0, 1, 2])
        assert [child.state for child in children] == (
            ["failed", "completed"] if recover else ["failed"] * 3
        )
        assert len(model.requests) == 2  # One decomposition and one actual consolidation.
        summarized = json.loads(model.requests[-1]["messages"][-1]["content"])["UNTRUSTED_DATA"]
        assert {item["execution_id"]: item["state"] for item in summarized} == {
            str(child.id): child.state for child in children
        }
        assert not any(child.tools_used for child in children)
    finally:
        for provider in gateway.providers.values():
            await provider.client.aclose()
        if child_gateway:
            for provider in child_gateway.providers.values():
                await provider.client.aclose()


@pytest.mark.parametrize(
    "content_type,size,accepted",
    [
        ("application/json", 100, False),
        ("application/octet-stream", 100, False),
        ("text/csv", 100, False),
        ("", 100, False),
        ("text/plain", MAX_BYTES + 1, False),
        ("text/html; charset=utf-8", MAX_BYTES, True),
    ],
)
def test_research_enforces_mime_and_byte_limit_and_closes_connection(
    monkeypatch, content_type, size, accepted
):
    import app.services.ai.research as research

    monkeypatch.setenv("WORKFORCE_RESEARCH_ALLOWED_HOSTS", "public.example")
    monkeypatch.setattr(research, "resolve_public", lambda host: "93.184.216.34")
    reads, closed = [], []

    class Response:
        status = 200

        def getheader(self, name, default=""):
            return content_type if name == "Content-Type" else default

        def read(self, limit):
            reads.append(limit)
            return b"a" * min(limit, size)

    class Connection:
        def __init__(self, host, address):
            assert (host, address) == ("public.example", "93.184.216.34")

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            closed.append(True)

    monkeypatch.setattr(research, "PinnedHTTPSConnection", Connection)
    if accepted:
        result = fetch_public("https://public.example/docs", ["https://public.example/docs"])
        assert result["truncated"] and result["untrusted"] and len(result["content"]) == 12000
    else:
        with pytest.raises(HTTPException) as exc:
            fetch_public("https://public.example/docs", ["https://public.example/docs"])
        assert exc.value.status_code == 422
    assert closed == [True]
    assert reads == (
        [MAX_BYTES + 1] if content_type.startswith(("text/plain", "text/html")) else []
    )
