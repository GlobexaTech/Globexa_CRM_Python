"""Dictionary-only conditions and substitutions. No expression interpreter."""
import html
import json
import re
from fastapi import HTTPException
from app.services.ai.safety import safe_data

FIELDS = {
    "lead": {"id", "title", "description", "status", "stage", "score", "ai_score", "first_name", "email", "owner_id", "contact_id", "company_id", "source"},
    "contact": {"id", "first_name", "last_name", "email", "phone", "company", "company_id", "do_not_contact", "email_opted_out"},
    "deal": {"id", "title", "description", "value", "stage_id", "pipeline_id", "owner_id", "contact_id", "lead_id"},
    "task": {"id", "title", "description", "status", "priority", "owner_id", "lead_id", "deal_id"},
    "message": {"id", "body", "subject", "conversation_id", "direction", "status", "recipient"},
    "campaign": {"id", "name", "status", "sent", "replied", "opened"},
    "current_user": {"id", "name"}, "automation": {"execution_id", "id", "version", "chain_id"},
    "event": {"id", "type", "aggregate_id"},
}
OUTPUT_FIELDS = {"id", "job_id", "status", "decision", "reason", "confidence", "summary", "classification", "score", "recommendation", "draft", "reasons", "health", "stalled", "stage_days", "action", "priority", "duplicate_ids", "matched", "approval_id", "execution_id"}
OPS = {"eq", "ne", "contains", "not_contains", "starts_with", "ends_with", "gt", "lt", "gte", "lte", "empty", "not_empty", "exists", "changed", "changed_to", "changed_from"}
PATH = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,2}$")
TEMPLATE = re.compile(r"{{\s*([^{}]+?)\s*}}")
MISSING = object()


def validate_path(path, variables=(), nodes=()):
    if not isinstance(path, str) or not PATH.fullmatch(path) or "__" in path:
        raise ValueError("Invalid variable path")
    bits = path.split(".")
    valid = (len(bits) == 2 and bits[0] in FIELDS and bits[1] in FIELDS[bits[0]])
    valid |= len(bits) == 2 and bits[0] == "vars" and bits[1] in variables
    valid |= len(bits) == 3 and bits[0] == "steps" and bits[1] in nodes and bits[2] in OUTPUT_FIELDS
    if not valid:
        raise ValueError("Unknown or protected variable: " + path)


def get_value(context, path, default=None):
    current = context
    for bit in path.split("."):
        if not isinstance(current, dict) or bit not in current:
            return default
        current = current[bit]
    return current


def validate_condition(condition, variables=(), nodes=(), depth=0, budget=None):
    budget = budget if budget is not None else [0]
    budget[0] += 1
    if depth > 8 or budget[0] > 64 or not isinstance(condition, dict):
        raise ValueError("Condition tree exceeds bounds")
    groups = set(condition) & {"all", "any", "not"}
    if groups:
        if len(condition) != 1:
            raise ValueError("A condition group has one operator")
        key = next(iter(groups))
        children = [condition[key]] if key == "not" else condition[key]
        if not isinstance(children, list) or not 1 <= len(children) <= 32:
            raise ValueError("Condition group needs 1-32 children")
        for child in children:
            validate_condition(child, variables, nodes, depth + 1, budget)
        return
    if set(condition) - {"field", "operator", "value"} or condition.get("operator") not in OPS:
        raise ValueError("Unsupported condition")
    validate_path(condition.get("field"), variables, nodes)
    safe_data(condition.get("value"))


def evaluate(condition, context, before=None):
    if "all" in condition:
        return all(evaluate(c, context, before) for c in condition["all"])
    if "any" in condition:
        return any(evaluate(c, context, before) for c in condition["any"])
    if "not" in condition:
        return not evaluate(condition["not"], context, before)
    field, op = condition["field"], condition["operator"]
    value, target = get_value(context, field, MISSING), condition.get("value")
    old = get_value(before or {}, field, MISSING)
    empty = value is MISSING or value is None or value == "" or value == []
    if op == "exists": return value is not MISSING
    if op == "empty": return empty
    if op == "not_empty": return not empty
    if op.startswith("changed"):
        changed = old is not MISSING and value is not MISSING and old != value
        return changed and (op == "changed" or (value if op == "changed_to" else old) == target)
    if value is MISSING: return False
    if op == "eq": return value == target
    if op == "ne": return value != target
    if op in {"contains", "not_contains", "starts_with", "ends_with"}:
        if not isinstance(value, str) or not isinstance(target, str): return False
        result = {"contains": target in value, "not_contains": target not in value,
                  "starts_with": value.startswith(target), "ends_with": value.endswith(target)}
        return result[op]
    if isinstance(value, bool) or isinstance(target, bool) or not isinstance(value, (float, int)) or not isinstance(target, (float, int)):
        return False
    return {"gt": value > target, "lt": value < target, "gte": value >= target, "lte": value <= target}[op]


def validate_templates(value, variables=(), nodes=()):
    if isinstance(value, dict):
        for item in value.values(): validate_templates(item, variables, nodes)
    elif isinstance(value, list):
        for item in value: validate_templates(item, variables, nodes)
    elif isinstance(value, str):
        for match in TEMPLATE.finditer(value): validate_path(match[1], variables, nodes)
        if "{{" in TEMPLATE.sub("", value) or "}}" in TEMPLATE.sub("", value) or "{%" in value:
            raise ValueError("Only named variable substitutions are supported")


def render(value, context, *, html_destination=False):
    if isinstance(value, dict): return {key: render(item, context, html_destination=html_destination) for key, item in value.items()}
    if isinstance(value, list): return [render(item, context, html_destination=html_destination) for item in value]
    if not isinstance(value, str): return value
    def lookup(match):
        resolved = get_value(context, match[1], MISSING)
        if resolved is MISSING or isinstance(resolved, (dict, list)):
            raise HTTPException(422, "A template variable is unavailable or not scalar")
        return resolved
    whole = TEMPLATE.fullmatch(value)
    if whole and not html_destination:
        return lookup(whole)
    def substitute(match):
        output = str(lookup(match))
        return html.escape(output, quote=True) if html_destination else output
    result = TEMPLATE.sub(substitute, value)
    if len(result) > 12000: raise HTTPException(422, "Rendered content exceeds limit")
    return result


def bounded_context(value):
    if not isinstance(value, dict) or len(json.dumps(value, default=str)) > 48000:
        raise HTTPException(422, "Automation context exceeds bounds")
    if set(value) - (set(FIELDS) | {"steps", "vars", "before"}):
        raise HTTPException(422, "Unknown context namespace")
