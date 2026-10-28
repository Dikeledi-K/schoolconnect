"""Weeks 3-4: analytics figures and weekly summary insights.

Tickets are built by hand at known times (school time, Africa/Johannesburg) so every expected
figure can be worked out on paper. The report week is Monday 2 - Sunday 8 March 2026 (no
public holidays); "now" is Monday 9 March 2026 at 14:00.
"""

import json
from datetime import date, datetime, timedelta, timezone
from itertools import count
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app.analytics.insights import build_insights, executive_summary, rate_text, template_summary
from app.analytics.metrics import compute_metrics, last_full_week, period_bounds, weekly_trends
from app.config import Settings
from app.models import AIAuditLog, Ticket, TicketEvent
from app.taxonomy import CATEGORIES, DEPARTMENT_NAMES, categories_for_department

SA = ZoneInfo("Africa/Johannesburg")
NOW = datetime(2026, 3, 9, 14, 0, tzinfo=SA)
WEEK = (date(2026, 3, 2), date(2026, 3, 8))
_refs = count(1)


def at(day: int, hour: int, minute: int = 0, month: int = 3) -> datetime:
    """A moment in school time, converted to UTC: the app always stores UTC (SQLite keeps no timezone)."""
    return datetime(2026, month, day, hour, minute, tzinfo=SA).astimezone(timezone.utc)


def add(db, created, category="academic", urgency="low", first=None, resolved=None, contact=None,
        language="en", grade="4", safety=False):
    status = "resolved" if resolved else ("in_progress" if first else "new")
    t = Ticket(reference=f"SC-20260302-{next(_refs):04d}", message="SECRET MESSAGE TEXT", learner_grade=grade,
               channel="web", category=category, urgency=urgency, language=language,
               routed_role=CATEGORIES[category].routed_role, confidence=0.9, method="rules",
               needs_human=False, safety_flag=safety, reason="", status=status, created_at=created,
               updated_at=created, first_response_at=first, resolved_at=resolved, parent_contact=contact)
    db.add(t)
    db.commit()
    return t


def metrics(db, scope="school"):
    return compute_metrics(db, *WEEK, scope, now=NOW)


# ---------------------------------------------------------------- periods
def test_period_bounds_use_school_time(db_session):
    lo, hi = period_bounds(*WEEK)
    assert lo == datetime(2026, 3, 1, 22, 0, tzinfo=timezone.utc)
    assert hi == datetime(2026, 3, 8, 22, 0, tzinfo=timezone.utc)
    add(db_session, at(8, 23, 30))                     # Sunday 23:30 school time: in the week
    add(db_session, at(9, 0, 30))                      # Monday 00:30: next week
    assert metrics(db_session)["volume"]["total"] == 1


def test_last_full_week():
    assert last_full_week(date(2026, 3, 11)) == WEEK
    assert last_full_week(date(2026, 3, 9)) == WEEK     # on Monday, last week is the full one


def test_period_validation(db_session):
    with pytest.raises(ValueError):
        compute_metrics(db_session, date(2026, 3, 8), date(2026, 3, 2), now=NOW)
    with pytest.raises(ValueError):
        compute_metrics(db_session, date(2025, 1, 1), date(2026, 3, 8), now=NOW)


# ---------------------------------------------------------------- volume
def test_volume_by_topic_and_change_on_previous_week(db_session):
    for day in (2, 3, 4):
        add(db_session, at(day, 9))
    add(db_session, at(5, 9), category="fees_exemptions")
    add(db_session, at(24, 9, month=2))                # previous week
    add(db_session, at(25, 9, month=2))
    v = metrics(db_session)["volume"]
    assert (v["total"], v["previous"], v["change_pct"]) == (4, 2, 100)
    assert v["by_category"]["academic"] == {**v["by_category"]["academic"], "n": 3, "previous": 2, "change": 1}
    assert v["by_category"]["fees_exemptions"]["n"] == 1
    assert v["busiest_day"]["n"] == 1 and v["by_weekday"]["Monday"] == 1
    assert sum(d["n"] for d in v["by_day"]) == 4 and len(v["by_day"]) == 7


# ---------------------------------------------------------------- response times
def test_response_time_counts_office_hours_only(db_session):
    # Friday 15:00 -> Monday 08:30 = 0.5 h on Friday + 1.0 h on Monday (the weekend does not count)
    add(db_session, at(6, 15), first=at(9, 8, 30), resolved=at(9, 10, 30))
    r = metrics(db_session)["response"]
    assert r["first_response"]["median"] == 1.5
    assert r["resolution"]["median"] == 3.5


def test_answered_on_time_met_missed_pending(db_session):
    # medium = 2 school days: Monday 10:00 is due Wednesday 10:00
    add(db_session, at(2, 10), urgency="medium", first=at(3, 9))      # met
    add(db_session, at(2, 10), urgency="medium", first=at(5, 9))      # late
    add(db_session, at(2, 10), urgency="medium")                      # never answered: late
    add(db_session, at(6, 14), urgency="medium")                      # due Tue 10 Mar: still pending
    add(db_session, at(7, 20), urgency="critical", first=at(7, 20, 30))   # critical: 1 clock hour, met
    on_time = metrics(db_session)["response"]["on_time"]
    assert on_time == {"met": 2, "missed": 2, "pending": 1, "rate": 0.5}


def test_backlog_is_as_at_end_of_week(db_session):
    add(db_session, at(4, 9), first=at(4, 10), resolved=at(9, 9))     # resolved on Monday after: open at week end
    add(db_session, at(2, 10), urgency="medium")                      # never answered: overdue
    add(db_session, at(3, 9), first=at(3, 10), resolved=at(3, 12))   # closed in the week
    b = metrics(db_session)["backlog"]
    assert b == {"open": 2, "overdue": 1, "oldest_open_days": 6}   # Mon 2 Mar 10:00 -> end of Sun 8 Mar


# ---------------------------------------------------------------- departments, escalations, privacy
def test_department_only_sees_its_own_topics(db_session):
    add(db_session, at(2, 9), category="fees_exemptions")
    add(db_session, at(2, 9), category="academic")
    m = metrics(db_session, "finance_clerk")
    assert m["volume"]["total"] == 1 and list(m["volume"]["by_category"]) == ["fees_exemptions"]
    assert m["scope"]["name"] == DEPARTMENT_NAMES["finance_clerk"]
    assert categories_for_department("school") == list(CATEGORIES)
    with pytest.raises(ValueError):
        categories_for_department("janitor")


def test_escalations_repeat_contacts_and_no_personal_data(db_session):
    a = add(db_session, at(2, 9), contact="Parent@Example.com ")
    add(db_session, at(3, 9), contact="parent@example.com")           # same parent, different case
    add(db_session, at(3, 9), contact="other@example.com")
    db_session.add(TicketEvent(ticket_id=a.id, type="escalated", from_value="x", to_value="y", actor="system"))
    db_session.commit()
    m = metrics(db_session)
    assert m["escalations"] == 1 and m["repeat_contacts"] == 1
    dump = json.dumps(m)
    assert "example.com" not in dump and "SECRET MESSAGE" not in dump


def test_weekly_trends_fill_empty_weeks(db_session):
    add(db_session, at(17, 9, month=2), first=at(17, 10, month=2))    # week of 16 Feb
    add(db_session, at(3, 9), first=at(3, 11))                        # week of 2 Mar
    rows = weekly_trends(db_session, "school", weeks=3, end=date(2026, 3, 8), now=NOW)
    assert [r["week_start"] for r in rows] == ["2026-02-16", "2026-02-23", "2026-03-02"]
    assert [r["total"] for r in rows] == [1, 0, 1]
    assert rows[1]["median_first_response"] is None and rows[2]["median_first_response"] == 2.0


# ---------------------------------------------------------------- insights
def test_rate_text_never_hides_a_missed_target():
    assert rate_text(0.895, 0.9) == "89.5%"
    assert rate_text(0.95, 0.9) == "95%" and rate_text(0.5, 0.9) == "50%"


def test_insights_flag_slower_replies_and_missed_promises(db_session):
    add(db_session, at(24, 9, month=2), first=at(24, 10, month=2))    # previous week: 1 h
    add(db_session, at(2, 9), urgency="medium", first=at(4, 15))      # this week: slow and late
    add(db_session, at(2, 9), urgency="medium", first=at(2, 15))      # 6 h, on time
    insights = build_insights(metrics(db_session))
    concerns = [i["text"] for i in insights if i["type"] == "concern"]
    assert any(t.startswith("Replies were slower") for t in concerns)
    assert any("Only 50% of messages were answered within the promised time (target 90%); 1 was late." == t
               for t in concerns)
    assert insights[0]["text"].startswith("2 parent messages, up 100% on the previous week (1)")


def test_insights_use_correct_plurals(db_session):
    a = add(db_session, at(2, 9), first=at(2, 10))
    db_session.add(TicketEvent(ticket_id=a.id, type="escalated", actor="system"))
    db_session.commit()
    texts = " ".join(i["text"] for i in build_insights(metrics(db_session)))
    assert "1 message was escalated" in texts and "(s)" not in texts


def test_executive_summary_template_and_ai(db_session):
    add(db_session, at(2, 9), first=at(2, 10))
    m = metrics(db_session)
    ins = build_insights(m)
    text, method = executive_summary(db_session, m, ins, Settings(llm_provider="rules"))
    assert method == "template" and text == template_summary(m, ins)

    ai = Settings(llm_provider="anthropic", anthropic_api_key="test-key")
    numbers_ok = "A calm week: 1 parent message, answered quickly (within 1.0 office hours)."
    with patch("app.analytics.insights.generate_text", return_value=numbers_ok):
        text, method = executive_summary(db_session, m, ins, ai)
    assert method == "anthropic" and text == numbers_ok

    with patch("app.analytics.insights.generate_text", return_value="1 message; next week expect 250."):
        text, method = executive_summary(db_session, m, ins, ai)
    assert method == "template" and "250" not in text
    rows = db_session.query(AIAuditLog).filter(AIAuditLog.feature == "report_summary").all()
    assert len(rows) == 2 and rows[1].fallback_reason.startswith("AI summary rejected")


def test_outlook_uses_the_week5_forecast(history_sessionmaker):
    from app.analytics.insights import outlook

    with history_sessionmaker() as db:
        look = outlook(db, "school", date(2026, 1, 12))
        welfare = outlook(db, "deputy_principal", date(2026, 1, 12))
    assert look["expected_messages"] > 100 and look["week_end"] == "2026-01-18"
    assert welfare["expected_messages"] < look["expected_messages"]
    assert all(s["topic"] for s in look["spikes"])
