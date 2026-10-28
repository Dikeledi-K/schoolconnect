"""Week 7: auto-assignment by role and open work (hours), with child-safety routing."""

from app.models import Outbox, Staff, Ticket
from app.workflow.assignment import open_hours
from tests.conftest import add_staff

ADMISSIONS = "Is there still space for Grade 1 next year?"          # admin_clerk, 15 min
TRANSPORT = "The scholar transport bus was late this morning"       # admin_clerk, 8 min
MISSING = "My son did not come home from school yesterday"          # welfare, critical


def _ticket(client, message):
    r = client.post("/tickets", json={"message": message})
    assert r.status_code == 201
    return client.get(f"/tickets/{r.json()['id']}").json()


def _give(db_session, staff, category, count, status="new"):
    """Pretend `staff` already holds `count` tickets of this category."""
    for i in range(count):
        db_session.add(Ticket(reference=f"SC-20200101-{staff.id}{category[:3]}{i}{status[:1]}", message="x",
                              category=category, urgency="low", language="en", routed_role=staff.role,
                              method="rules", status=status, assigned_to=staff.id))
    db_session.commit()


def test_goes_to_the_person_with_least_open_hours_not_fewest_tickets(client, db_session):
    a = add_staff(db_session, "Ms A", "admin_clerk")
    b = add_staff(db_session, "Mr B", "admin_clerk")
    _give(db_session, a, "admissions", 1)          # 15 min
    _give(db_session, b, "transport", 1)           # 8 min
    _give(db_session, b, "other", 1)               # 5 min  -> 13 min, but 2 tickets
    assert open_hours(db_session, a.id) == 15 / 60 and open_hours(db_session, b.id) == 13 / 60
    t = _ticket(client, ADMISSIONS)
    assert t["assigned_to"] == b.id
    event = [e for e in client.get(f"/tickets/{t['id']}/events").json() if e["type"] == "assigned"][0]
    assert event["actor"] == "system" and "Mr B" in event["to_value"] and "0.2 h" in event["from_value"]


def test_resolved_tickets_are_not_open_work_but_break_ties(client, db_session):
    a = add_staff(db_session, "Ms A", "admin_clerk")
    b = add_staff(db_session, "Mr B", "admin_clerk")
    _give(db_session, a, "admissions", 3, status="resolved")   # 0 open hours, but 3 assignments
    assert open_hours(db_session, a.id) == 0
    assert _ticket(client, TRANSPORT)["assigned_to"] == b.id   # tie on hours -> fewer assignments wins
    assert _ticket(client, TRANSPORT)["assigned_to"] == a.id   # now b has 8 open minutes, a has 0


def test_balances_between_two_people(client, db_session):
    a = add_staff(db_session, "Ms A", "admin_clerk")
    b = add_staff(db_session, "Mr B", "admin_clerk")
    owners = [_ticket(client, TRANSPORT)["assigned_to"] for _ in range(4)]
    assert owners == [a.id, b.id, a.id, b.id]


def test_inactive_staff_are_skipped(client, db_session):
    add_staff(db_session, "Ms Away", "finance_clerk", active=False)
    here = add_staff(db_session, "Mrs Pillay", "finance_clerk")
    assert _ticket(client, "Please send me the fee statement")["assigned_to"] == here.id


def test_nobody_in_the_role_leaves_it_in_the_queue_with_a_reason(client, db_session):
    t = _ticket(client, "I forgot my portal password")         # no IT support account exists
    assert t["assigned_to"] is None
    event = [e for e in client.get(f"/tickets/{t['id']}/events").json() if e["type"] == "unassigned"][0]
    assert "No active IT Support" in event["to_value"]


def test_welfare_and_critical_go_to_the_deputy_principal(client, db_session):
    add_staff(db_session, "Mr Nel", "class_teacher")
    deputy = add_staff(db_session, "Mr Mokoena", "deputy_principal")
    assert _ticket(client, "My daughter is being bullied at break")["assigned_to"] == deputy.id
    assert _ticket(client, MISSING)["assigned_to"] == deputy.id


def test_critical_goes_to_the_principal_when_there_is_no_deputy(client, db_session):
    principal = db_session.query(Staff).filter_by(role="principal").one()     # the `client` login
    assert _ticket(client, MISSING)["assigned_to"] == principal.id


def test_new_critical_alerts_deputy_and_principal(client, db_session):
    deputy = add_staff(db_session, "Mr Mokoena", "deputy_principal")
    t = _ticket(client, MISSING)
    rows = db_session.query(Outbox).filter_by(ticket_id=t["id"]).all()
    kinds = {(r.recipient, r.kind) for r in rows}
    assert (deputy.email, "staff_assigned") in kinds                   # the owner
    assert ("principal@test.example", "staff_new_critical") in kinds   # also told at once
    for r in rows:   # welfare: the reference only
        assert r.body == f"New learner welfare ticket {t['reference']}, open SchoolConnect."


def test_parent_response_does_not_reveal_the_assignee(anon_client, db_session):
    add_staff(db_session, "Mrs Pillay", "finance_clerk")
    r = anon_client.post("/tickets", json={"message": "Please send me the fee statement"}).json()
    assert "assigned_to" not in r and "Pillay" not in str(r)
