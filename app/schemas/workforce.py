"""Strict public contracts for the bounded, accountable AI workforce."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

AgentName = Literal["research", "lead_mining", "sales", "analyst", "support", "supervisor"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ExecutionContext(Strict):
    entity_type: Literal["lead", "contact", "deal", "conversation", "campaign"] | None = None
    entity_id: UUID | None = None
    untrusted_text: str = Field("", max_length=12000)
    research_urls: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def relation(self):
        if bool(self.entity_type) != bool(self.entity_id):
            raise ValueError("Entity type and ID must be supplied together")
        return self


class ExecutionInput(Strict):
    agent_name: AgentName
    objective: str = Field(min_length=3, max_length=4000)
    context: ExecutionContext = Field(default_factory=ExecutionContext)
    tools: list[str] = Field(default_factory=list, max_length=16)


class ExecutionResponse(Strict):
    id: UUID
    agent_name: str
    task_type: str
    state: str
    task: dict
    tools_used: list
    result: dict | None = None
    error_message: str | None = None
    provider: str | None = None
    model: str | None = None
    parent_id: UUID | None = None
    attempts: int
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None


class ExecutionDetail(ExecutionResponse):
    children: list[ExecutionResponse] = Field(default_factory=list)


class ApprovalResponse(Strict):
    id: UUID
    agent_name: str
    requesting_user_id: UUID | None
    execution_id: UUID | None
    action_type: str
    target: str | None
    proposed_action: dict
    action_hash: str
    status: str
    created_at: datetime
    expires_at: datetime | None
    decided_at: datetime | None
    decided_by: UUID | None
    rejection_reason: str | None
    execution_result: dict | None


class ApprovalDecision(Strict):
    decision: Literal["approved", "rejected"]
    action_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str | None = Field(None, max_length=1000)


class MemoryInput(Strict):
    agent_name: AgentName
    key: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_. -]+$")
    value: dict[str, Any]
    retention_days: int = Field(30, ge=1, le=90)


class MemoryResponse(Strict):
    id: UUID
    agent_name: str
    memory_type: str
    key: str
    value: dict
    actor_id: UUID | None
    approved_by: UUID | None
    execution_id: UUID | None
    created_at: datetime
    expires_at: datetime | None
