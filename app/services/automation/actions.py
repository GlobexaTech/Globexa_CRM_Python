"""Actions reuse existing tools/services; custom actions have explicit permission/schema maps."""

from typing import Literal
from uuid import UUID
from fastapi import HTTPException
from pydantic import Field, EmailStr
from app.schemas.automation import Strict
from app.services.ai.workforce_tools import (
    TOOL_SPECS,
    validate_ownership,
    execute_tool,
    action_binding,
)
from app.services.crm.common import authorize, owned, audit
from app.services.crm.automation import perform_action, relations
from app.services.ai.safety import safe_data
from app.models import Contact, Lead, Deal, Task, Conversation, AutomationNotification


class ContactCreate(Strict):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=50)
    company_id: UUID | None = None


class ContactUpdate(Strict):
    contact_id: UUID
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=50)


class DealStage(Strict):
    entity_id: UUID
    stage_id: UUID


class Owner(Strict):
    entity_id: UUID
    owner_id: UUID


class Tag(Strict):
    entity_type: Literal["lead", "contact", "deal", "task"]
    entity_id: UUID
    tag: str = Field(min_length=1, max_length=80, pattern=r"^[\w .-]+$")


class Start(Strict):
    automation_id: UUID


class Stop(Strict):
    execution_id: UUID


class Notification(Strict):
    message: str = Field(min_length=1, max_length=2000)


class Webhook(Strict):
    url: str = Field(min_length=8, max_length=1000)
    payload: dict = Field(default_factory=dict)


class ApprovalGate(Strict):
    reason: str = Field(min_length=1, max_length=2000)


EXTRA = {
    "create_contact": ("contacts:write", ContactCreate),
    "update_contact": ("contacts:write", ContactUpdate),
    "change_deal_stage": ("deals:write", DealStage),
    "assign_owner": ("leads:assign", Owner),
    "add_tag": ("automation:write", Tag),
    "remove_tag": ("automation:write", Tag),
    "start_automation": ("automation:write", Start),
    "stop_automation": ("automation:write", Stop),
    "create_notification": ("automation:write", Notification),
    "webhook_call": ("integrations:webhooks", Webhook),
    "request_approval": ("automation:write", ApprovalGate),
}
STANDARD = {name for name, spec in TOOL_SPECS.items() if spec[2]}
ACTIONS = STANDARD | set(EXTRA) | {"send_whatsapp"}
EXTERNAL = {"send_email", "send_whatsapp", "webhook_call"}


def canonical(name):
    return "send_email" if name == "send_whatsapp" else name


def schema_for(name):
    if name not in ACTIONS:
        raise HTTPException(422, "Unsupported automation action")
    return TOOL_SPECS[canonical(name)][1] if canonical(name) in STANDARD else EXTRA[name][1]


def arguments_for(name, args):
    safe_data(args)
    if name in {"create_task", "create_note"} and not any(
        args.get(key) for key in ("lead_id", "deal_id", "contact_id", "company_id")
    ):
        raise HTTPException(422, "A customer relation is required")
    return schema_for(name).model_validate(args).model_dump(mode="json", exclude_none=True)


async def permitted(db, tenant_id, actor_id, name, args):
    args = arguments_for(name, args)
    if canonical(name) in STANDARD:
        await validate_ownership(db, tenant_id, actor_id, canonical(name), args)
        if name in {"send_email", "send_whatsapp"}:
            conversation = await owned(db, Conversation, tenant_id, UUID(args["conversation_id"]))
            if (conversation.channel == "whatsapp") != (name == "send_whatsapp"):
                raise HTTPException(422, "Send action does not match conversation channel")
        return args
    await authorize(db, tenant_id, actor_id, EXTRA[name][0])
    if name in {"create_contact", "update_contact"}:
        await relations(db, tenant_id, {k: UUID(v) for k, v in args.items() if k.endswith("_id")})
    if name in {"assign_owner", "change_deal_stage"}:
        await owned(
            db, Lead if name == "assign_owner" else Deal, tenant_id, UUID(args["entity_id"])
        )
        await relations(
            db, tenant_id, {"owner_id": UUID(args["owner_id"])} if "owner_id" in args else {}
        )
    if name in {"add_tag", "remove_tag"}:
        await authorize(db, tenant_id, actor_id, args["entity_type"] + "s:write")
        await owned(
            db,
            {"lead": Lead, "contact": Contact, "deal": Deal, "task": Task}[args["entity_type"]],
            tenant_id,
            UUID(args["entity_id"]),
        )
    if name == "webhook_call":
        from app.services.automation.webhook import validate_destination

        validate_destination(args["url"])
    if name == "start_automation":
        from app.models import Automation

        await owned(db, Automation, tenant_id, UUID(args["automation_id"]))
    if name == "stop_automation":
        from app.models import AutomationExecution

        await owned(db, AutomationExecution, tenant_id, UUID(args["execution_id"]))
    return args


async def binding(db, tenant_id, name, args):
    return (
        await action_binding(db, tenant_id, canonical(name), args)
        if canonical(name) in STANDARD
        else {}
    )


async def execute(db, tenant_id, actor_id, name, args, key, execution):
    args = await permitted(db, tenant_id, actor_id, name, args)
    if canonical(name) in STANDARD:
        return await execute_tool(
            db, tenant_id, actor_id, canonical(name), args, key, approved=True
        )
    if name == "create_contact":
        row = Contact(
            tenant_id=tenant_id,
            created_by_id=actor_id,
            **{k: UUID(v) if k.endswith("_id") else v for k, v in args.items()},
        )
        db.add(row)
        await db.flush()
        result = {"id": str(row.id)}
    elif name == "update_contact":
        row = await owned(db, Contact, tenant_id, UUID(args["contact_id"]), True)
        for field, value in args.items():
            if field != "contact_id":
                setattr(row, field, value)
        row.updated_by_id = actor_id
        result = {"id": str(row.id)}
    elif name in {"assign_owner", "change_deal_stage"}:
        result = await perform_action(
            db,
            tenant_id,
            actor_id,
            "update_deal" if name == "change_deal_stage" else name,
            args,
            key,
        )
    elif name in {"add_tag", "remove_tag"}:
        row = await owned(
            db,
            {"lead": Lead, "contact": Contact, "deal": Deal, "task": Task}[args["entity_type"]],
            tenant_id,
            UUID(args["entity_id"]),
            True,
        )
        tags = set((row.custom_fields or {}).get("automation_tags", []))
        if name == "add_tag":
            tags.add(args["tag"])
        else:
            tags.discard(args["tag"])
        if len(tags) > 50:
            raise HTTPException(422, "Entity tag limit reached")
        row.custom_fields = {**(row.custom_fields or {}), "automation_tags": sorted(tags)}
        result = {"id": str(row.id), "tags": sorted(tags)}
    elif name == "create_notification":
        row = AutomationNotification(
            tenant_id=tenant_id,
            execution_id=execution.id,
            user_id=actor_id,
            message=args["message"],
        )
        db.add(row)
        await db.flush()
        result = {"id": str(row.id)}
    elif name == "start_automation":
        from app.services.automation.engine import request_execution

        row = await request_execution(
            db,
            tenant_id,
            actor_id,
            UUID(args["automation_id"]),
            execution.input.get("entity", {}),
            key,
            parent=execution,
        )
        result = {"execution_id": str(row.id)}
    elif name == "stop_automation":
        from app.services.automation.engine import transition_execution

        row = await transition_execution(
            db, tenant_id, actor_id, UUID(args["execution_id"]), "cancel"
        )
        result = {"execution_id": str(row.id), "status": row.state}
    elif name == "request_approval":
        result = {"approved": True}
    elif name == "webhook_call":
        from app.services.automation.webhook import deliver

        result = await deliver(args["url"], args["payload"], key)
    else:
        raise HTTPException(422, "Unsupported automation action")
    audit(
        db, tenant_id, actor_id, "automation.action." + name, "automation_execution", execution.id
    )
    return result
