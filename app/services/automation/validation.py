"""Publishing rejects invalid graphs, schemas, references, permissions and configuration."""
import os
import re
from uuid import UUID
from fastapi import HTTPException
from app.schemas.automation import Definition, Limits
from app.services.automation.expressions import validate_condition, validate_templates, TEMPLATE
from app.services.automation.actions import ACTIONS, EXTERNAL, schema_for, arguments_for, permitted, EXTRA, canonical, STANDARD
from app.services.ai.workforce_tools import TOOL_SPECS
from app.services.ai.safety import safe_data
from app.services.crm.common import authorize, owned
from app.models import Integration, Conversation, AutomationPolicy
from sqlalchemy import select

AI_KINDS = {"summarize", "classify", "score", "recommend", "research", "draft", "extract"}


async def policy(db, tenant_id):
    row = await db.scalar(select(AutomationPolicy).where(AutomationPolicy.tenant_id == tenant_id))
    return Limits.model_validate(row.limits if row else {})


def successors(nodes, index):
    node = nodes[index]
    default = nodes[index + 1].id if index + 1 < len(nodes) else None
    return node.next if node.next is not None else default, node.on_false, node.fallback


def validate_structure(definition):
    definition = Definition.model_validate(definition)
    ids = [node.id for node in definition.nodes]
    if len(set(ids)) != len(ids): raise ValueError("Node IDs must be unique")
    if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key) or "__" in key for key in definition.variables):
        raise ValueError("Invalid variable name")
    safe_data(definition.variables)
    edges = {}
    for index, node in enumerate(definition.nodes):
        safe_data(node.arguments)
        validate_templates(node.arguments, definition.variables, ids)
        edges[node.id] = [target for target in successors(definition.nodes, index) if target]
        if any(target not in ids for target in edges[node.id]): raise ValueError("Unknown graph edge")
        if node.on_error == "fallback" and not node.fallback: raise ValueError("Fallback requires an action node")
        if node.fallback and definition.nodes[ids.index(node.fallback)].type != "action": raise ValueError("Fallback must target an action")
        if node.type == "condition":
            validate_condition(node.condition, definition.variables, ids)
        elif node.type == "delay":
            if set(node.arguments) - {"seconds", "minutes", "hours", "days", "until", "condition", "poll_seconds", "timeout_seconds"}:
                raise ValueError("Unknown delay option")
            modes = set(node.arguments) & {"seconds", "minutes", "hours", "days", "until", "condition"}
            if len(modes) != 1: raise ValueError("Select exactly one wait mode")
            mode = next(iter(modes))
            if mode in {"seconds", "minutes", "hours", "days"}:
                value = node.arguments[mode]
                if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value * {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}[mode] <= 2592000:
                    raise ValueError("Wait duration must be between zero and 30 days")
            elif mode == "until":
                from pydantic import TypeAdapter, AwareDatetime
                TypeAdapter(AwareDatetime).validate_python(node.arguments["until"])
            else:
                validate_condition(node.arguments["condition"], definition.variables, ids)
                if not 5 <= node.arguments.get("poll_seconds", 60) <= 3600 or not 1 <= node.arguments.get("timeout_seconds", 86400) <= 2592000:
                    raise ValueError("Wait polling/timeout exceeds bounds")
        elif node.type in {"ai", "ai_decision"}:
            if set(node.arguments) - {"kind", "instruction", "url"}: raise ValueError("Unknown AI option")
            if node.arguments.get("kind", "summarize") not in AI_KINDS: raise ValueError("Unsupported AI action")
            if not isinstance(node.arguments.get("instruction", ""), str) or len(node.arguments.get("instruction", "")) > 2000: raise ValueError("AI instruction too long")
            if node.arguments.get("kind") == "research":
                from app.services.ai.research import validate_url
                validate_url(node.arguments.get("url", ""), [node.arguments.get("url", "")])
        elif node.type == "intelligence":
            if set(node.arguments) - {"kind", "entity_type", "entity_id"} or node.arguments.get("kind") not in {"lead", "deal", "campaign", "customer", "next_best_action"}:
                raise ValueError("Unknown intelligence action")
        else:
            action = "request_approval" if node.type == "approval" else node.action
            if action not in ACTIONS: raise ValueError("Unsupported action")
            spec = schema_for(action).model_json_schema()
            args = dict(node.arguments)
            # Validate static fields and shape while substituting only the types of
            # explicitly allowlisted runtime variables; real ownership is rechecked later.
            for field, value in args.items():
                if isinstance(value, str) and TEMPLATE.search(value):
                    prop = spec.get("properties", {}).get(field, {})
                    options = prop.get("anyOf", [prop])
                    real = next((p for p in options if p.get("type") != "null"), prop)
                    if real.get("format") == "uuid": args[field] = "00000000-0000-4000-8000-000000000001"
                    elif real.get("format") == "email": args[field] = "variable@example.com"
                    elif real.get("type") == "integer": args[field] = 0
                    elif real.get("type") == "boolean": args[field] = False
                    else: args[field] = "value"
            arguments_for(action, args)
    seen, visiting = set(), set()
    def visit(node):
        if node in visiting: raise ValueError("Workflow graph contains a cycle")
        if node in seen: return
        visiting.add(node)
        for target in edges[node]: visit(target)
        visiting.remove(node); seen.add(node)
    for node in ids: visit(node)
    if definition.schedule:
        from app.services.automation.scheduling import next_occurrence
        from app.services.crm.common import now
        if next_occurrence(definition.schedule.model_dump(mode="json"), now()) is None:
            raise ValueError("One-time schedule must be in the future")
    return definition


async def validate_publish(db, tenant_id, actor_id, definition):
    definition = validate_structure(definition)
    limits = await policy(db, tenant_id)
    await authorize(db, tenant_id, actor_id, "automation:write")
    if len(definition.nodes) > limits.max_steps: raise HTTPException(422, "Workflow exceeds configured step quota")
    for integration_id in definition.credentials.values():
        await authorize(db, tenant_id, actor_id, "integrations:read")
        integration = await owned(db, Integration, tenant_id, integration_id)
        if integration.status != "connected": raise HTTPException(422, "Referenced provider is not connected")
    for node in definition.nodes:
        if node.type in {"ai", "ai_decision"}:
            await authorize(db, tenant_id, actor_id, "ai:chat")
            if limits.max_ai_calls == 0 or limits.daily_ai_calls == 0 or limits.monthly_ai_calls == 0:
                raise HTTPException(403, "AI automation usage is disabled")
            from app.services.crm.ai import build_gateway
            try:
                gateway = build_gateway()
            except (RuntimeError, ValueError): raise HTTPException(422, "Configure an approved AI provider/model before publishing") from None
            for provider in gateway.providers.values(): await provider.client.aclose()
        if node.type not in {"action", "approval"}: continue
        name = "request_approval" if node.type == "approval" else node.action
        permission = TOOL_SPECS[canonical(name)][0] if canonical(name) in STANDARD else EXTRA[name][0]
        await authorize(db, tenant_id, actor_id, permission)
        templated = any(isinstance(value, str) and TEMPLATE.search(value) for value in node.arguments.values())
        if not templated: await permitted(db, tenant_id, actor_id, name, node.arguments)
        if name in {"send_email", "send_whatsapp"}:
            if "{{" in str(node.arguments.get("conversation_id")):
                if not definition.credentials: raise HTTPException(422, "Dynamic sends require an explicit credential reference")
            else:
                conversation = await owned(db, Conversation, tenant_id, UUID(node.arguments["conversation_id"]))
                if conversation.integration_id not in definition.credentials.values():
                    raise HTTPException(422, "Send provider must be explicitly referenced by the version")
            for integration_id in definition.credentials.values():
                from app.services.crm.providers import adapter_for
                integration = await owned(db, Integration, tenant_id, integration_id)
                if "send" not in adapter_for(integration).capabilities: raise HTTPException(422, "Referenced provider cannot send messages")
        if name == "webhook_call":
            from app.services.automation.webhook import validate_destination
            validate_destination(node.arguments.get("url", ""))
    return definition
