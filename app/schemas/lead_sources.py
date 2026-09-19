"""Validated configuration for lead-source create and partial update."""

from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, create_model
from app.models import IntegrationTypeEnum, LeadStatusEnum


class LeadSourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=255)
    source_type: IntegrationTypeEnum
    description: str | None = Field(None, max_length=10000)
    default_utm_source: str | None = Field(None, max_length=100)
    default_utm_medium: str | None = Field(None, max_length=100)
    default_utm_campaign: str | None = Field(None, max_length=100)
    auto_create_contact: bool = True
    auto_create_company: bool = True
    default_lead_status: LeadStatusEnum = LeadStatusEnum.NEW
    default_owner_id: UUID | None = None
    deduplication_fields: list[Literal["email", "phone"]] = Field(
        default_factory=lambda: ["email"], max_length=2
    )
    icon: str | None = Field(None, max_length=100)
    color: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    is_active: bool = True
    sort_order: int = Field(0, ge=0, le=100000)
    custom_fields: dict = Field(default_factory=dict)


# Preserve each field's constraints; absent values are distinct from explicit null.
LeadSourcePatch = create_model(
    "LeadSourcePatch",
    __config__=ConfigDict(extra="forbid"),
    **{
        name: (field.rebuild_annotation(), None)
        for name, field in LeadSourceInput.model_fields.items()
    },
)
