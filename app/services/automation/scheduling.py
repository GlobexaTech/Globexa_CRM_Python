"""Bounded IANA-zone schedules. DST gaps skip; repeated local times run once (fold 0)."""

from datetime import datetime, timedelta, timezone as utc_timezone
from app.schemas.automation import Schedule, BusinessHours, timezone


def cron_field(value, low, high):
    result = set()
    if len(value) > 40:
        raise ValueError("Cron field too long")
    for part in value.split(","):
        pieces = part.split("/")
        if len(pieces) > 2:
            raise ValueError("Invalid cron step")
        step = int(pieces[1]) if len(pieces) == 2 else 1
        if step < 1 or step > high - low + 1:
            raise ValueError("Invalid cron step")
        base = pieces[0]
        if base == "*":
            start, end = low, high
        elif "-" in base:
            bounds = base.split("-")
            if len(bounds) != 2:
                raise ValueError("Invalid cron range")
            start, end = map(int, bounds)
        else:
            start = end = int(base)
        if not low <= start <= end <= high:
            raise ValueError("Cron value out of range")
        result.update(range(start, end + 1, step))
    return sorted(result)


def parse_cron(expression):
    pieces = expression.split()
    if len(pieces) != 5:
        raise ValueError("Cron requires minute, hour, day, month and weekday")
    bounds = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
    return pieces, [cron_field(part, *bound) for part, bound in zip(pieces, bounds)]


def next_occurrence(configuration, after):
    spec = Schedule.model_validate(configuration)
    if after.tzinfo is None:
        raise ValueError("Schedule anchor must be timezone-aware")
    if spec.kind == "once":
        return spec.at if spec.at > after else None
    zone = timezone(spec.timezone)
    start = after.astimezone(zone).date()
    if spec.kind == "cron":
        raw, (minutes, hours, days, months, weekdays) = parse_cron(spec.cron)
    else:
        hours, minutes = [[int(v)] for v in spec.time.split(":")]
    for offset in range(367):
        day = start + timedelta(days=offset)
        if spec.kind == "weekly" and day.weekday() != spec.weekday:
            continue
        if spec.kind == "monthly" and day.day != spec.day:
            continue
        if spec.kind == "cron":
            if day.month not in months:
                continue
            dom, dow = day.day in days, (day.weekday() + 1) % 7 in weekdays
            match = (dom or dow) if raw[2] != "*" and raw[4] != "*" else (dom and dow)
            if not match:
                continue
        for hour in hours:
            for minute in minutes:
                local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone, fold=0)
                candidate = local.astimezone(utc_timezone.utc)
                if candidate.astimezone(zone).replace(tzinfo=None) != local.replace(tzinfo=None):
                    continue
                if candidate > after:
                    return candidate
    raise ValueError("Schedule has no occurrence within 366 days")


def business_open(configuration, instant):
    if not configuration:
        return True
    spec = BusinessHours.model_validate(configuration)
    if spec.allow_outside_hours:
        return True
    local = instant.astimezone(timezone(spec.timezone))
    return (
        local.weekday() in spec.weekdays
        and local.date().isoformat() not in spec.holidays
        and spec.start <= local.strftime("%H:%M") < spec.end
    )


def next_business_open(configuration, instant):
    if business_open(configuration, instant):
        return instant
    spec = BusinessHours.model_validate(configuration)
    zone = timezone(spec.timezone)
    day = instant.astimezone(zone).date()
    hour, minute = map(int, spec.start.split(":"))
    for offset in range(367):
        current = day + timedelta(days=offset)
        candidate = datetime(current.year, current.month, current.day, hour, minute, tzinfo=zone)
        if candidate > instant and business_open(configuration, candidate):
            return candidate.astimezone(utc_timezone.utc)
    raise ValueError("No business hours available within one year")
