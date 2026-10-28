"""Week 3: turn tickets into measurable figures for one period and one department.

Every figure is a count or a time. No names, contact details or message text ever leave this
module, so the dashboard and the weekly reports are safe to share with the SGB (POPIA).

Times are counted in OFFICE HOURS (Monday-Friday 07:30-15:30, minus public holidays, from
config/workflow.yaml and the Week 5 calendar): the hours the school could actually respond.
A message sent on Friday at 15:00 and answered on Monday at 08:30 took 1.5 office hours
(half an hour on Friday, one hour on Monday), not 65 clock hours.

"Answered on time" uses the same first-response promise as the Week 7 SLA
(config/workflow.yaml first_response, which matches config/school_info.yaml).

Which moment are figures measured at?
- Response times and promises: for messages RECEIVED in the period, using everything known
  when the figures are calculated. A Friday-evening message answered on Monday morning counts
  as answered in a report made on Monday afternoon.
- Backlog ("still open"): as at the END of the period.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Response, Ticket, TicketEvent
from app.risk.fairness import grade_band
from app.taxonomy import (
    CATEGORIES,
    DEPARTMENT_NAMES,
    LANGUAGES,
    SCHOOL_SCOPE,
    URGENCY_LEVELS,
    WELFARE_CATEGORY,
    categories_for_department,
)
from app.workflow.sla import add_school_days, aware, clock_start, load_workflow, office_hours_between, tz

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
GRADE_BANDS = ["Foundation (R-3)", "Intermediate (4-6)", "Senior (7-9)", "FET (10-12)", "Not given"]
MAX_PERIOD_DAYS = 366


# --------------------------------------------------------------------------
# Periods (local school dates -> UTC database bounds)
# --------------------------------------------------------------------------
def period_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """UTC [from, to) bounds for the local dates start..end INCLUSIVE."""
    z = tz()
    lo = datetime.combine(start, time.min, tzinfo=z).astimezone(timezone.utc)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=z).astimezone(timezone.utc)
    return lo, hi


def local_date(moment: datetime) -> date:
    return aware(moment).astimezone(tz()).date()


def today_local(now: datetime | None = None) -> date:
    return local_date(now or datetime.now(timezone.utc))


def last_full_week(today: date | None = None) -> tuple[date, date]:
    """Monday and Sunday of the most recent COMPLETED week."""
    today = today or today_local()
    this_monday = today - timedelta(days=today.weekday())
    return this_monday - timedelta(days=7), this_monday - timedelta(days=1)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def first_response_due(ticket: Ticket) -> datetime:
    """The ORIGINAL first-response promise (ignores later escalations, which only happen once
    that promise is already missed)."""
    target = load_workflow()["first_response"][ticket.urgency]
    start = aware(ticket.created_at)
    if "hours" in target:
        return start + timedelta(hours=target["hours"])
    return add_school_days(clock_start(start), target["school_days"])


def first_response_time(ticket: Ticket) -> datetime | None:
    """When the parent first heard back. Older tickets (Week 1 seed) only have resolved_at."""
    moment = ticket.first_response_at or ticket.resolved_at
    return aware(moment) if moment else None


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def time_stats(hours: list[float]) -> dict:
    """Median and 90th percentile, rounded for display. None when there is no data."""
    if not hours:
        return {"n": 0, "median": None, "p90": None}
    return {"n": len(hours), "median": round(median(hours), 1), "p90": round(_percentile(hours, 0.9), 1)}


def change_pct(current: float | None, previous: float | None) -> int | None:
    """Percentage change, or None when there is nothing to compare with."""
    if current is None or not previous:
        return None
    return round((current - previous) / previous * 100)


def _tickets(db: Session, scope: str, lo: datetime, hi: datetime) -> list[Ticket]:
    query = select(Ticket).where(Ticket.created_at >= lo, Ticket.created_at < hi,
                                 Ticket.category.in_(categories_for_department(scope)))
    return list(db.scalars(query))


def _counts(tickets: list[Ticket], key, keys: list[str]) -> dict[str, int]:
    counts = {k: 0 for k in keys}
    for t in tickets:
        value = key(t)
        counts[value] = counts.get(value, 0) + 1
    return counts


# --------------------------------------------------------------------------
# Response times and promises
# --------------------------------------------------------------------------
def response_block(tickets: list[Ticket], now: datetime) -> dict:
    first, resolution = [], []
    met = missed = pending = 0
    for t in tickets:
        responded = first_response_time(t)
        if responded and responded <= now:
            first.append(office_hours_between(t.created_at, responded))
        if t.resolved_at and aware(t.resolved_at) <= now:
            resolution.append(office_hours_between(t.created_at, t.resolved_at))
        due = first_response_due(t)
        if responded and responded <= now:
            met, missed = (met + 1, missed) if responded <= due else (met, missed + 1)
        elif now > due:
            missed += 1                       # no response yet and the promise has passed
        else:
            pending += 1                      # not answered yet, but still within the promise
    judged = met + missed
    return {
        "first_response": time_stats(first),
        "resolution": time_stats(resolution),
        "on_time": {"met": met, "missed": missed, "pending": pending,
                    "rate": round(met / judged, 3) if judged else None},
    }


# --------------------------------------------------------------------------
# The main calculation
# --------------------------------------------------------------------------
def compute_metrics(db: Session, start: date, end: date, scope: str = SCHOOL_SCOPE,
                    now: datetime | None = None) -> dict:
    """All dashboard figures for local dates start..end (inclusive), compared with the
    previous period of the same length."""
    if end < start:
        raise ValueError("The end date is before the start date")
    days = (end - start).days + 1
    if days > MAX_PERIOD_DAYS:
        raise ValueError(f"Choose a period of at most {MAX_PERIOD_DAYS} days")
    now = aware(now or datetime.now(timezone.utc))
    cats = categories_for_department(scope)

    lo, hi = period_bounds(start, end)
    prev_start, prev_end = start - timedelta(days=days), start - timedelta(days=1)
    plo, phi = period_bounds(prev_start, prev_end)
    cur, prev = _tickets(db, scope, lo, hi), _tickets(db, scope, plo, phi)
    measured_at = min(now, hi)                # backlog is "as at" the end of the period (or now)

    # ---- Volume
    cur_cats, prev_cats = _counts(cur, lambda t: t.category, cats), _counts(prev, lambda t: t.category, cats)
    cur_resp = response_block(cur, now)
    by_category = {}
    for c in cats:
        subset = [t for t in cur if t.category == c]
        by_category[c] = {"name": CATEGORIES[c].display_name, "n": cur_cats[c], "previous": prev_cats[c],
                          "change": cur_cats[c] - prev_cats[c],
                          "median_first_response": response_block(subset, now)["first_response"]["median"]}
    daily = Counter(local_date(t.created_at) for t in cur)
    by_day = [{"date": (start + timedelta(days=i)).isoformat(), "n": daily.get(start + timedelta(days=i), 0)}
              for i in range(days)]
    busiest = max(by_day, key=lambda d: d["n"]) if cur else None
    weekdays = Counter(local_date(t.created_at).weekday() for t in cur)

    # ---- Backlog at the end of the period (still open, and open past the promise)
    open_query = select(Ticket).where(Ticket.created_at < measured_at, Ticket.category.in_(cats),
                                      (Ticket.resolved_at.is_(None)) | (Ticket.resolved_at > measured_at))
    still_open = list(db.scalars(open_query))
    overdue_open = [t for t in still_open
                    if (first_response_time(t) is None or first_response_time(t) > measured_at)
                    and first_response_due(t) < measured_at]
    oldest = max(((measured_at - aware(t.created_at)).days for t in still_open), default=0)

    # ---- Escalations (Week 7 events) and approved replies (Week 6) in the period
    ids = [t.id for t in cur]
    escalations = 0
    approved = edited = 0
    if ids:
        escalations = len(list(db.scalars(select(TicketEvent.id).where(
            TicketEvent.type == "escalated", TicketEvent.ticket_id.in_(ids)))))
        for r in db.scalars(select(Response).where(Response.ticket_id.in_(ids), Response.status == "approved")):
            approved += 1
            edited += bool(r.edited)

    # ---- Parents who wrote more than once (a sign the first message was not answered)
    contacts = Counter(t.parent_contact.strip().lower() for t in cur if t.parent_contact)
    repeat_contacts = sum(1 for n in contacts.values() if n > 1)

    return {
        "scope": {"key": scope, "name": DEPARTMENT_NAMES[scope]},
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days,
                   "previous_start": prev_start.isoformat(), "previous_end": prev_end.isoformat(),
                   "measured_at": measured_at.isoformat(timespec="minutes")},
        "volume": {
            "total": len(cur), "previous": len(prev), "change_pct": change_pct(len(cur), len(prev)),
            "by_category": by_category,
            "by_urgency": _counts(cur, lambda t: t.urgency, list(URGENCY_LEVELS)),
            "by_language": {LANGUAGES.get(k, k): v for k, v in
                            _counts(cur, lambda t: t.language, list(LANGUAGES)).items()},
            "by_channel": dict(Counter(t.channel for t in cur)),
            "by_grade_band": _counts(cur, lambda t: grade_band(t.learner_grade), GRADE_BANDS),
            "by_weekday": {WEEKDAY_NAMES[i]: weekdays.get(i, 0) for i in range(7)},
            "by_day": by_day,
            "busiest_day": busiest,
        },
        "response": {**cur_resp, "previous": response_block(prev, now)},
        "backlog": {"open": len(still_open), "overdue": len(overdue_open), "oldest_open_days": oldest},
        "escalations": escalations,
        "repeat_contacts": repeat_contacts,
        "safety": {"welfare": sum(t.category == WELFARE_CATEGORY for t in cur),
                   "critical": sum(t.urgency == "critical" for t in cur),
                   "safety_flagged": sum(bool(t.safety_flag) for t in cur)},
        "replies": {"approved": approved, "edited_by_staff": edited},
        "sla_target_rate": load_workflow().get("sla_target_rate", 0.9),
    }


def weekly_trends(db: Session, scope: str = SCHOOL_SCOPE, weeks: int = 12, end: date | None = None,
                  now: datetime | None = None) -> list[dict]:
    """One row per week (Monday start) for the last `weeks` complete weeks up to `end` (a Sunday)."""
    weeks = max(1, min(int(weeks), 52))
    now = aware(now or datetime.now(timezone.utc))
    end = end or last_full_week(today_local(now))[1]
    first_monday = end - timedelta(days=end.weekday()) - timedelta(weeks=weeks - 1)
    lo, hi = period_bounds(first_monday, first_monday + timedelta(weeks=weeks) - timedelta(days=1))
    tickets = _tickets(db, scope, lo, hi)
    by_week: dict[date, list[Ticket]] = {}
    for t in tickets:
        d = local_date(t.created_at)
        by_week.setdefault(d - timedelta(days=d.weekday()), []).append(t)
    rows = []
    for i in range(weeks):
        monday = first_monday + timedelta(weeks=i)
        subset = by_week.get(monday, [])
        resp = response_block(subset, now)
        rows.append({
            "week_start": monday.isoformat(), "total": len(subset),
            "by_category": _counts(subset, lambda t: t.category, categories_for_department(scope)),
            "median_first_response": resp["first_response"]["median"],
            "on_time_rate": resp["on_time"]["rate"],
        })
    return rows
