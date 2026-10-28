"""Response-time targets (SLAs): when is a ticket's first response due, and is it late?

How the clock works (rules in config/workflow.yaml):
- Critical: 1 clock hour from arrival, day or night.
- Other urgencies count SCHOOL DAYS (Mon-Fri office days, minus public holidays from the
  Week 5 calendar). The clock starts at the next office opening if the message arrives
  outside office hours; the response is due at the same time of day N school days later.
  Example: a "high" message on Friday 10:00 is due Monday 10:00; one sent on Saturday is
  due Tuesday 07:30.
- After an escalation the clock restarts (the new owner gets a full window).
- The target is met once the ticket is acknowledged: moved out of "new", or a first response
  recorded (status change or approved reply).

Time left / overdue is counted in OFFICE hours for school-day targets (a weekend does not make
a ticket "60 hours late"), and in clock hours for critical tickets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from app.forecasting.calendar import load_calendar
from app.models import Ticket

WORKFLOW_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "workflow.yaml"


@lru_cache
def load_workflow(path: str = str(WORKFLOW_FILE)) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def public_holidays() -> frozenset[date]:
    days = []
    for year in load_calendar()["years"].values():
        days += [date.fromisoformat(d) for d in year.get("public_holidays", [])]
    return frozenset(days)


def tz() -> ZoneInfo:
    return ZoneInfo(load_workflow()["timezone"])


def _clock(name: str) -> time:
    return time.fromisoformat(load_workflow()["office_hours"][name])


def aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes (stored as UTC); make them timezone-aware."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_office_day(d: date) -> bool:
    return d.weekday() < 5 and d not in public_holidays()


def office_window(d: date) -> tuple[datetime, datetime]:
    """Opening and closing time on day d, in school time."""
    return (datetime.combine(d, _clock("start"), tzinfo=tz()), datetime.combine(d, _clock("end"), tzinfo=tz()))


def next_office_day(d: date) -> date:
    d += timedelta(days=1)
    while not is_office_day(d):
        d += timedelta(days=1)
    return d


def clock_start(moment: datetime) -> datetime:
    """When the school-day clock starts: now if the office is open, else the next opening."""
    local = aware(moment).astimezone(tz())
    d = local.date()
    if is_office_day(d):
        opens, closes = office_window(d)
        if local < opens:
            return opens
        if local < closes:
            return local
    return office_window(next_office_day(d))[0]


def add_school_days(start: datetime, days: int) -> datetime:
    """Same time of day, `days` office days later (start must be inside office hours)."""
    d = start.date()
    for _ in range(days):
        d = next_office_day(d)
    return datetime.combine(d, start.timetz())


def office_hours_between(a: datetime, b: datetime) -> float:
    """Office hours from a to b (0 if b <= a). Weekends and public holidays count as 0."""
    a, b = aware(a).astimezone(tz()), aware(b).astimezone(tz())
    total, d = 0.0, a.date()
    while d <= b.date():
        if is_office_day(d):
            opens, closes = office_window(d)
            overlap = (min(b, closes) - max(a, opens)).total_seconds()
            total += max(0.0, overlap)
        d += timedelta(days=1)
    return total / 3600


def due_at(ticket: Ticket) -> datetime:
    """When the first response is due (from arrival, or from the last escalation)."""
    target = load_workflow()["first_response"][ticket.urgency]
    start = aware(ticket.escalated_at or ticket.created_at)
    if "hours" in target:
        return start + timedelta(hours=target["hours"])
    return add_school_days(clock_start(start), target["school_days"])


def is_acknowledged(ticket: Ticket) -> bool:
    return ticket.first_response_at is not None or ticket.status != "new"


def _duration(hours: float) -> str:
    hours = abs(hours)
    if hours < 1:
        return f"{max(1, round(hours * 60))} min"
    return f"{hours:.0f} h" if hours >= 10 or hours == int(hours) else f"{hours:.1f} h"


@dataclass
class SlaStatus:
    status: str          # on_track | due_soon | overdue | met
    due_at: datetime
    hours_left: float    # negative = overdue (office hours; clock hours for critical)
    label: str           # "2 h left", "overdue 3 h", "responded"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["due_at"] = self.due_at.isoformat()
        d["hours_left"] = round(self.hours_left, 2)
        return d


def sla_status(ticket: Ticket, now: datetime | None = None) -> SlaStatus:
    now = aware(now or datetime.now(timezone.utc))
    due = due_at(ticket)
    if is_acknowledged(ticket):
        return SlaStatus("met", due, 0.0, "resolved" if ticket.status == "resolved" else "responded")
    if ticket.urgency == "critical":           # clock hours
        left = (due - now).total_seconds() / 3600
    elif now < due:
        left = office_hours_between(now, due)
    else:
        left = -office_hours_between(due, now)
    if now >= due:
        return SlaStatus("overdue", due, min(left, 0.0), f"overdue {_duration(left)}")
    soon = load_workflow()["due_soon_hours"][ticket.urgency]
    return SlaStatus("due_soon" if left <= soon else "on_track", due, left, f"{_duration(left)} left")


def due_text(ticket: Ticket) -> str:
    """For staff alerts, e.g. "Mon 02 Mar 10:00"."""
    return due_at(ticket).astimezone(tz()).strftime("%a %d %b %H:%M")
