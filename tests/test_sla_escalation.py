"""Week 7: SLA maths (weekends, public holidays, office hours) and idempotent escalation.

Every test uses a fixed "now": no sleeping, no dependence on today's date.
2026 calendar facts used: Fri 3 April (Good Friday) and Mon 6 April (Family Day) are public holidays.
"""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.models import AIAuditLog, Outbox, Ticket
from app.responses.templates import load_school_info
from app.workflow.escalation import run_escalations
from app.workflow.sla import (add_school_days, clock_start, due_at, load_workflow, office_hours_between,
                              sla_status)
from tests.conftest import add_staff

SAST = ZoneInfo("Africa/Johannesburg")


def at(text: str) -> datetime:
    """'2026-03-06 10:00' in school time."""
    return datetime.fromisoformat(text).replace(tzinfo=SAST)


def ticket(urgency="high", created="2026-03-06 10:00", status="new", **extra) -> Ticket:
    return Ticket(reference="SC-TEST", message="x", category="academic", urgency=urgency, language="en",
                  routed_role="class_teacher", method="rules", status=status, created_at=at(created),
                  escalation_level=0, **extra)


# ---- Config matches the promises to parents --------------------------------
def test_targets_match_school_info_response_times():
    promises = load_school_info()["response_times"]
    targets = load_workflow()["first_response"]
    assert set(promises) == set(targets)
    for urgency, target in targets.items():
        if "school_days" in target:
            n = target["school_days"]
            assert re.search(rf"\b{n} school days?\b", promises[urgency]), urgency
    assert targets["critical"] == {"hours": 1} and "today" in promises["critical"]
    assert load_workflow()["office_hours"] == {"start": "07:30", "end": "15:30"}
    assert "07:30 to 15:30" in load_school_info()["school"]["office_hours"]


# ---- Clock maths ------------------------------------------------------------
@pytest.mark.parametrize("created,urgency,due", [
    ("2026-03-06 10:00", "high", "2026-03-09 10:00"),      # Friday -> Monday (weekend skipped)
    ("2026-03-06 17:00", "high", "2026-03-10 07:30"),      # after hours: clock starts Mon 07:30
    ("2026-03-07 11:00", "high", "2026-03-10 07:30"),      # Saturday: same
    ("2026-03-09 06:00", "high", "2026-03-10 07:30"),      # before opening on Monday
    ("2026-04-02 10:00", "high", "2026-04-07 10:00"),      # Easter: Fri 3 + Mon 6 April are holidays
    ("2026-04-02 14:00", "medium", "2026-04-08 14:00"),    # 2 school days over Easter
    ("2026-03-02 09:00", "low", "2026-03-09 09:00"),       # 5 school days = one week
    ("2026-03-07 22:00", "critical", "2026-03-07 23:00"),  # critical: 1 clock hour, even at night
])
def test_due_dates(created, urgency, due):
    assert due_at(ticket(urgency, created)) == at(due)


def test_clock_start_and_school_days():
    assert clock_start(at("2026-04-02 16:00")) == at("2026-04-07 07:30")   # Thu evening before Easter
    assert add_school_days(at("2026-04-02 08:00"), 1) == at("2026-04-07 08:00")


def test_office_hours_between_skips_nights_weekends_and_holidays():
    assert office_hours_between(at("2026-03-06 15:00"), at("2026-03-09 08:30")) == 1.5
    assert office_hours_between(at("2026-04-02 15:30"), at("2026-04-07 07:30")) == 0.0
    assert office_hours_between(at("2026-03-09 07:30"), at("2026-03-10 07:30")) == 8.0
    assert office_hours_between(at("2026-03-10 09:00"), at("2026-03-09 09:00")) == 0.0


def test_sla_status_on_track_due_soon_overdue():
    t = ticket("high", "2026-03-06 10:00")                        # due Mon 10:00
    s = sla_status(t, at("2026-03-06 11:00"))
    assert (s.status, s.hours_left, s.label) == ("on_track", 7.0, "7 h left")   # 4.5 Fri + 2.5 Mon
    s = sla_status(t, at("2026-03-09 08:30"))
    assert (s.status, s.label) == ("due_soon", "1.5 h left")
    s = sla_status(t, at("2026-03-09 13:00"))
    assert (s.status, s.hours_left, s.label) == ("overdue", -3.0, "overdue 3 h")


def test_critical_sla_counts_clock_minutes():
    t = ticket("critical", "2026-03-07 22:00")
    assert sla_status(t, at("2026-03-07 22:30")).label == "30 min left"
    assert sla_status(t, at("2026-03-07 22:50")).status == "due_soon"
    assert sla_status(t, at("2026-03-08 00:00")).label == "overdue 1 h"


def test_acknowledged_tickets_have_met_their_target():
    assert sla_status(ticket(status="in_progress"), at("2026-03-20 09:00")).status == "met"
    t = ticket(first_response_at=at("2026-03-06 10:30"))
    assert sla_status(t, at("2026-03-20 09:00")).label == "responded"


def test_escalation_restarts_the_clock():
    t = ticket("high", "2026-03-06 10:00", escalated_at=at("2026-03-09 13:00"))
    assert due_at(t) == at("2026-03-10 13:00")


# ---- Escalation ---------------------------------------------------------------
def _db_ticket(client, db_session, message, urgency, created, routed_role=None, category=None):
    r = client.post("/tickets", json={"message": message})
    assert r.status_code == 201
    t = db_session.get(Ticket, r.json()["id"])
    t.urgency, t.created_at = urgency, at(created)
    if routed_role:
        t.routed_role, t.category = routed_role, category
    db_session.commit()
    return t


def _events(client, t, type_):
    return [e for e in client.get(f"/tickets/{t.id}/events").json() if e["type"] == type_]


def test_overdue_ticket_moves_one_level_up_and_is_idempotent(client, db_session):
    teacher = add_staff(db_session, "Mr Nel", "class_teacher")
    deputy = add_staff(db_session, "Mr Mokoena", "deputy_principal")
    t = _db_ticket(client, db_session, "When is the exam timetable out?", "high", "2026-03-06 10:00")
    assert t.assigned_to == teacher.id

    now = at("2026-03-09 13:00")                       # 3 office hours overdue
    first = run_escalations(db_session, now)
    assert first["escalated"] == [{"reference": t.reference, "to_role": "deputy_principal", "level": 1}]
    assert t.assigned_to == deputy.id and t.escalation_level == 1

    assert run_escalations(db_session, now)["escalated"] == []                        # same breach: no-op
    assert run_escalations(db_session, now + timedelta(hours=2))["escalated"] == []   # new window running
    assert len(_events(client, t, "escalated")) == 1

    # The deputy also misses their (fresh) 1-school-day window -> principal.
    later = run_escalations(db_session, at("2026-03-10 14:00"))
    assert later["escalated"][0]["to_role"] == "principal" and t.escalation_level == 2
    # Top of the chain: reported, but nothing more to move and no duplicate events.
    for _ in range(2):
        top = run_escalations(db_session, at("2026-03-12 09:00"))
        assert top["escalated"] == [] and top["at_top_of_chain"] == [t.reference]
    assert len(_events(client, t, "escalation_top")) == 1


def test_escalation_logs_an_event_an_audit_row_and_notifies_without_details(client, db_session):
    add_staff(db_session, "Mrs Pillay", "finance_clerk")
    t = _db_ticket(client, db_session, "Please send my fee statement, my ID is 8001015009087",
                   "high", "2026-03-06 10:00")
    run_escalations(db_session, at("2026-03-09 13:00"))
    event = _events(client, t, "escalated")[0]
    assert "Finance Clerk" in event["from_value"] and "overdue 3 h" in event["from_value"]
    assert "Ms Dlamini" in event["to_value"]                     # admin/finance -> principal
    row = db_session.query(AIAuditLog).filter_by(ticket_id=t.id, feature="escalation").one()
    assert row.output["from_role"] == "finance_clerk" and row.output["to_role"] == "principal"
    alert = db_session.query(Outbox).filter_by(ticket_id=t.id, kind="staff_escalated").one()
    assert alert.recipient == "principal@test.example" and "Response due: Tue 10 Mar 13:00" in alert.body
    assert "8001015009087" not in alert.body and "statement" not in alert.body


def test_acknowledged_tickets_are_never_escalated(client, db_session):
    add_staff(db_session, "Mr Nel", "class_teacher")
    t = _db_ticket(client, db_session, "When is the exam timetable out?", "high", "2026-03-06 10:00")
    client.patch(f"/tickets/{t.id}/status", json={"status": "in_progress"})
    assert run_escalations(db_session, at("2026-03-20 09:00"))["checked"] == 0


def test_unacknowledged_critical_alerts_deputy_and_principal_once(client, db_session):
    deputy = add_staff(db_session, "Mr Mokoena", "deputy_principal")
    t = _db_ticket(client, db_session, "My son did not come home yesterday", "critical", "2026-03-07 22:00")
    assert run_escalations(db_session, at("2026-03-07 22:20"))["critical_alerts"] == []    # only 20 min
    assert run_escalations(db_session, at("2026-03-07 22:31"))["critical_alerts"] == [t.reference]
    assert run_escalations(db_session, at("2026-03-07 22:45"))["critical_alerts"] == []    # once only
    alerts = db_session.query(Outbox).filter_by(ticket_id=t.id, kind="staff_critical_unacknowledged").all()
    assert {a.recipient for a in alerts} == {deputy.email, "principal@test.example"}
    assert all(a.body == f"New learner welfare ticket {t.reference}, open SchoolConnect." for a in alerts)
    # After 1 hour it also escalates: deputy -> principal.
    assert run_escalations(db_session, at("2026-03-07 23:05"))["escalated"][0]["to_role"] == "principal"


def test_escalate_job_endpoint_needs_the_jobs_token(client, set_env):
    assert client.post("/jobs/escalate").status_code == 503
    set_env(JOBS_TOKEN="tok")
    assert client.post("/jobs/escalate", headers={"X-Jobs-Token": "bad"}).status_code == 401
    r = client.post("/jobs/escalate", headers={"X-Jobs-Token": "tok"})
    assert r.status_code == 200 and {"checked", "escalated", "critical_alerts"} <= set(r.json())


def test_my_work_lists_my_open_tickets_overdue_first(client, db_session, login_as):
    teacher, headers = login_as("class_teacher", "Mr Nel")
    old = _db_ticket(client, db_session, "When is the exam timetable out?", "low", "2026-01-05 09:00")
    new = client.post("/tickets", json={"message": "Can I meet my son's maths teacher?"}).json()
    rows = client.get("/workflow/my-work", headers=headers).json()
    assert [r["id"] for r in rows] == [old.id, new["id"]]
    assert rows[0]["sla"]["status"] == "overdue" and rows[0]["sla"]["label"].startswith("overdue")
    assert client.get("/workflow/my-work").json() == []          # the principal holds nothing
