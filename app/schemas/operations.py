"""Stable, bounded request and response contracts for CRM operations."""

from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    EmailStr,
    AwareDatetime,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Page(StrictModel):
    items: list[dict]
    total: int
    limit: int
    offset: int


class JobResponse(StrictModel):
    id: UUID
    kind: str
    status: str
    attempts: int
    result: dict
    error_code: str | None
    created_at: datetime


class ParticipantInput(StrictModel):
    address: str = Field(min_length=1, max_length=255)
    name: str | None = Field(default=None, max_length=255)


class ConversationInput(StrictModel):
    subject: str = Field(min_length=1, max_length=255)
    channel: Literal["email", "whatsapp", "social"] = "email"
    contact_id: UUID | None = None
    company_id: UUID | None = None
    lead_id: UUID | None = None
    integration_id: UUID | None = None
    participants: list[ParticipantInput] = Field(default_factory=list, max_length=20)


class ConversationResponse(StrictModel):
    id: UUID
    subject: str
    channel: str
    contact_id: UUID | None
    company_id: UUID | None
    lead_id: UUID | None
    integration_id: UUID | None
    unread_count: int
    last_message_at: datetime | None
    created_at: datetime


class Attachment(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(max_length=100)
    size: int = Field(ge=0, le=25_000_000)
    provider_attachment_id: str = Field(max_length=500)


class MessageInput(StrictModel):
    body: str = Field(min_length=1, max_length=100_000)
    recipient: EmailStr
    attachments: list[Attachment] = Field(default_factory=list, max_length=10)


class MessageResponse(StrictModel):
    id: UUID
    conversation_id: UUID
    body: str
    direction: str
    status: str
    sender: str | None
    recipient: str | None
    provider_message_id: str | None
    attachments: list[dict]
    occurred_at: datetime
    created_at: datetime


class CampaignPlan(StrictModel):
    integration_id: UUID
    contact_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    company_id: UUID | None = None
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=100_000)
    steps: list[dict] = Field(default_factory=list, max_length=10)
    trigger_event: (
        Literal[
            "lead.created", "contact.created", "deal.stage_changed", "task.completed"
        ]
        | None
    ) = None


class ScheduleInput(StrictModel):
    scheduled_at: AwareDatetime


class WorkflowActionInput(StrictModel):
    tool: Literal[
        "create_task",
        "update_lead",
        "update_deal",
        "add_note",
        "send_email",
        "assign_owner",
        "invoke_ai",
    ]
    arguments: dict = Field(default_factory=dict)


class WorkflowConditionInput(StrictModel):
    field: Literal["status", "stage_id", "ai_score", "value", "source", "direction"]
    operator: Literal["eq", "ne", "gt", "lt"] = "eq"
    value: str | int | float | bool | None


class WorkflowInput(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    trigger: Literal[
        "lead.created",
        "lead.updated",
        "deal.created",
        "deal.stage_changed",
        "task.overdue",
        "message.received",
        "campaign.completed",
    ]
    conditions: list[WorkflowConditionInput] = Field(
        default_factory=list, max_length=20
    )
    actions: list[WorkflowActionInput] = Field(min_length=1, max_length=10)


class ToggleInput(StrictModel):
    enabled: bool


class AIRequest(StrictModel):
    capability: Literal[
        "lead_score",
        "lead_summary",
        "next_best_action",
        "reply_analysis",
        "campaign_draft",
        "proposal_draft",
    ]
    entity_id: UUID


class AIBatchRequest(StrictModel):
    requests: list[AIRequest] = Field(min_length=1, max_length=25)


class ScoreOutput(StrictModel):
    score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(min_length=1, max_length=10)


class SummaryOutput(StrictModel):
    summary: str = Field(min_length=1, max_length=5000)


class ActionOutput(StrictModel):
    action: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(min_length=1, max_length=10)


class ReplyOutput(StrictModel):
    classification: Literal[
        "interested",
        "not_interested",
        "question",
        "objection",
        "meeting_request",
        "unsubscribe",
        "other",
    ]
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(max_length=2000)


class DraftOutput(StrictModel):
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=20000)


class OAuthCallback(StrictModel):
    state: str = Field(min_length=32, max_length=200)
    code: str = Field(min_length=1, max_length=4000)


class ActivityInput(StrictModel):
    subject: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    lead_id: UUID | None = None
    deal_id: UUID | None = None
    contact_id: UUID | None = None
    company_id: UUID | None = None

    @model_validator(mode="after")
    def relation(self):
        if not any((self.lead_id, self.deal_id, self.contact_id, self.company_id)):
            raise ValueError("An associated customer resource is required")
        return self


class ToolInput(StrictModel):
    arguments: dict = Field(default_factory=dict)


class CampaignCreateInput(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    type: Literal["broadcast", "sequence", "triggered"] = "broadcast"
    sending_domain_id: UUID | None = None
    sender_name: str = Field(min_length=1, max_length=255)
    sender_email: EmailStr
    reply_to_email: EmailStr | None = None
    tags: list[str] = Field(default_factory=list, max_length=30)
