"""Bounded declarative graph; no executable expressions or arbitrary action names."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


TRIGGERS = frozenset({"manual", "api", "scheduled", "lead.created", "lead.updated", "lead.stage_changed",
    "contact.created", "contact.updated", "deal.created", "deal.updated", "deal.stage_changed", "task.created",
    "task.completed", "message.received", "message.sent", "message.delivered", "message.failed",
    "campaign.completed", "form.submitted", "webhook.received", "integration.connected",
    "integration.disconnected", "AI.score_changed"})


class Limits(Strict):
    daily_executions: int = Field(1000, ge=1, le=100000)
    monthly_executions: int = Field(10000, ge=1, le=1000000)
    queued_executions: int = Field(100, ge=1, le=10000)
    max_steps: int = Field(64, ge=1, le=100)
    max_depth: int = Field(5, ge=1, le=10)
    max_runtime_seconds: int = Field(604800, ge=60, le=2592000)
    max_ai_calls: int = Field(5, ge=0, le=20)
    daily_ai_calls: int = Field(20, ge=0, le=10000)
    monthly_ai_calls: int = Field(200, ge=0, le=100000)
    tenant_per_minute: int = Field(120, ge=1, le=10000)
    provider_per_minute: int = Field(20, ge=1, le=1000)
    action_per_minute: int = Field(60, ge=1, le=1000)
    require_internal_approval: bool = False


class BusinessHours(Strict):
    timezone: str = "UTC"
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1, max_length=7)
    start: str = Field("09:00", pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    end: str = Field("17:00", pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    holidays: list[str] = Field(default_factory=list, max_length=366)
    allow_outside_hours: bool = False

    @model_validator(mode="after")
    def valid(self):
        timezone(self.timezone)
        if any(day not in range(7) for day in self.weekdays) or self.start >= self.end:
            raise ValueError("Business hours require valid weekdays and a same-day time range")
        for day in self.holidays:
            datetime.strptime(day, "%Y-%m-%d")
        return self


def timezone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("An installed IANA timezone is required") from None


class Schedule(Strict):
    kind: Literal["once", "daily", "weekly", "monthly", "cron"]
    timezone: str
    at: datetime | None = None
    time: str = Field("09:00", pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    weekday: int = Field(0, ge=0, le=6)
    day: int = Field(1, ge=1, le=31)
    cron: str | None = Field(None, max_length=100)

    @model_validator(mode="after")
    def valid(self):
        timezone(self.timezone)
        if self.kind == "once" and (not self.at or self.at.tzinfo is None):
            raise ValueError("One-time schedules need an offset-aware date")
        if self.kind == "cron" and not self.cron:
            raise ValueError("A five-field cron schedule is required")
        return self


class Node(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    type: Literal["condition", "action", "delay", "ai", "ai_decision", "approval", "intelligence"]
    action: str | None = Field(None, max_length=50)
    arguments: dict = Field(default_factory=dict)
    condition: dict | None = None
    next: str | None = None
    on_false: str | None = None
    on_error: Literal["stop", "continue", "fallback"] = "stop"
    fallback: str | None = None
    max_retries: int = Field(2, ge=0, le=5)
    backoff_seconds: int = Field(10, ge=1, le=3600)


class Definition(Strict):
    trigger: str
    nodes: list[Node] = Field(min_length=1, max_length=100)
    variables: dict = Field(default_factory=dict, max_length=30)
    credentials: dict[str, UUID] = Field(default_factory=dict, max_length=20)
    business_hours: BusinessHours | None = None
    schedule: Schedule | None = None

    @model_validator(mode="after")
    def trigger_valid(self):
        if self.trigger not in TRIGGERS:
            raise ValueError("Unsupported trigger")
        if (self.trigger == "scheduled") != (self.schedule is not None):
            raise ValueError("Scheduled triggers require a schedule, other triggers cannot have one")
        return self


class AutomationInput(Strict):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    definition: Definition


class ExecuteInput(Strict):
    entity_type: Literal["lead", "contact", "deal", "task", "message", "campaign"] | None = None
    entity_id: UUID | None = None

    @model_validator(mode="after")
    def entity_pair(self):
        if bool(self.entity_type) != bool(self.entity_id):
            raise ValueError("Both entity type and ID are required")
        return self


class SimulateInput(Strict):
    context: dict = Field(default_factory=dict)


class DecisionOutput(Strict):
    decision: bool
    reason: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)


class IntelligenceOutput(Strict):
    summary: str = Field(min_length=1, max_length=4000)
    classification: str | None = Field(None, max_length=100)
    score: int | None = Field(None, ge=0, le=100)
    recommendation: str | None = Field(None, max_length=2000)
    draft: str | None = Field(None, max_length=8000)
    extracted: dict[str, str] = Field(default_factory=dict, max_length=20)
    reasons: list[str] = Field(default_factory=list, max_length=20)
