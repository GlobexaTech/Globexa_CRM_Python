from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from app.services.automation.expressions import (
    validate_condition,
    evaluate,
    validate_templates,
    render,
)
from app.services.automation.scheduling import next_occurrence, business_open, parse_cron
from app.services.automation.validation import validate_structure


@pytest.mark.parametrize(
    "operator,value,target,expected",
    [
        ("eq", "qualified", "qualified", True),
        ("ne", "new", "qualified", True),
        ("contains", "Product request", "request", True),
        ("not_contains", "Product", "lost", True),
        ("starts_with", "Product", "Pro", True),
        ("ends_with", "Product", "duct", True),
        ("gt", 81, 80, True),
        ("lt", 79, 80, True),
        ("gte", 80, 80, True),
        ("lte", 80, 80, True),
        ("empty", None, None, True),
        ("not_empty", "value", None, True),
        ("exists", None, None, True),
        ("gt", "81", 80, False),
        ("gt", True, 0, False),
        ("contains", {}, "x", False),
    ],
)
def test_condition_operators(operator, value, target, expected):
    rule = {"field": "lead.score", "operator": operator, "value": target}
    validate_condition(rule)
    assert evaluate(rule, {"lead": {"score": value}}) is expected


def test_groups_and_missing_before_do_not_invent_changes():
    changed = {"field": "lead.stage", "operator": "changed_to", "value": "qualified"}
    rule = {
        "all": [
            changed,
            {"not": {"field": "lead.score", "operator": "lt", "value": 80}},
            {
                "any": [
                    {"field": "lead.email", "operator": "exists"},
                    {"field": "lead.score", "operator": "gt", "value": 90},
                ]
            },
        ]
    }
    validate_condition(rule)
    context = {"lead": {"stage": "qualified", "score": 85, "email": "person@example.com"}}
    assert evaluate(rule, context, {"lead": {"stage": "new"}})
    assert not evaluate(rule, context)


@pytest.mark.parametrize(
    "path",
    [
        "os.environ",
        "lead.__class__",
        "current_user.password",
        "lead.email.upper()",
        "vars.api_key",
        "steps.unknown.score",
    ],
)
def test_templates_reject_code_and_secrets(path):
    with pytest.raises(ValueError):
        validate_templates("{{" + path + "}}")


def test_templates_are_typed_and_destination_escaped():
    context = {"lead": {"score": 81, "first_name": '<img src=x onerror="attack">'}}
    assert render("{{lead.score}}", context) == 81
    assert "<img" not in render("Hello {{lead.first_name}}", context, html_destination=True)
    with pytest.raises(HTTPException):
        render("Hello {{contact.email}}", context)


def test_dst_gap_skips_and_fold_occurs_once():
    before = datetime(2026, 3, 8, 5, tzinfo=timezone.utc)
    result = next_occurrence(
        {"kind": "daily", "timezone": "America/New_York", "time": "02:30"}, before
    )
    assert result == datetime(2026, 3, 9, 6, 30, tzinfo=timezone.utc)
    spec = {"kind": "daily", "timezone": "America/New_York", "time": "01:30"}
    first = next_occurrence(spec, datetime(2026, 11, 1, 4, tzinfo=timezone.utc))
    assert first == datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)
    assert next_occurrence(spec, first) == datetime(2026, 11, 2, 6, 30, tzinfo=timezone.utc)


def test_month_end_cron_and_holidays():
    result = next_occurrence(
        {"kind": "monthly", "timezone": "Asia/Kolkata", "day": 31, "time": "09:00"},
        datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    assert result == datetime(2026, 5, 31, 3, 30, tzinfo=timezone.utc)
    result = next_occurrence(
        {"kind": "cron", "timezone": "UTC", "cron": "*/15 9-17 * * 1-5"},
        datetime(2026, 9, 18, 9, 1, tzinfo=timezone.utc),
    )
    assert result == datetime(2026, 9, 18, 9, 15, tzinfo=timezone.utc)
    assert not business_open(
        {"timezone": "Asia/Kolkata", "holidays": ["2026-09-18"]},
        datetime(2026, 9, 18, 5, tzinfo=timezone.utc),
    )
    for cron in ("* * * * * *", "*/0 * * * *", "60 * * * *", "@reboot", "$(cmd) * * * *"):
        with pytest.raises(ValueError):
            parse_cron(cron)


def test_graph_rejects_cycles_unknown_fields_and_bad_waits():
    good = {
        "trigger": "manual",
        "nodes": [{"id": "wait", "type": "delay", "arguments": {"seconds": 1}}],
    }
    assert validate_structure(good)
    for node in (
        {
            "id": "loop",
            "type": "condition",
            "condition": {"field": "lead.score", "operator": "gt", "value": 5},
            "next": "loop",
        },
        {"id": "wait", "type": "delay", "arguments": {"seconds": 1, "days": 1}},
        {"id": "shell", "type": "action", "action": "exec", "arguments": {}},
    ):
        with pytest.raises(ValueError):
            validate_structure({"trigger": "manual", "nodes": [node]})


def test_graph_rejects_future_output_dependencies():
    with pytest.raises(ValueError, match="preceding step"):
        validate_structure({"trigger": "manual", "nodes": [
            {"id": "first", "type": "action", "action": "create_notification", "arguments": {"message": "{{steps.later.summary}}"}},
            {"id": "later", "type": "ai", "arguments": {}},
        ]})


def test_whole_template_cannot_bypass_size_bound():
    with pytest.raises(HTTPException): render("{{lead.title}}", {"lead": {"title": "x" * 12001}})
