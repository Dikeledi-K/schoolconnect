"""Week 7: the startup migration (Week 6 database -> Week 7 schema) and ticket events."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql, sqlite

from app.db import add_column_sql, init_db, migrate
from app.models import Ticket

# The tickets table exactly as Weeks 1-6 created it (no Week 7 columns).
WEEK6_TICKETS = """
CREATE TABLE tickets (
    id INTEGER PRIMARY KEY, reference VARCHAR(20) UNIQUE, message TEXT, parent_name VARCHAR(120),
    parent_contact VARCHAR(120), learner_grade VARCHAR(4), channel VARCHAR(20), category VARCHAR(30),
    urgency VARCHAR(10), language VARCHAR(10), routed_role VARCHAR(30), confidence FLOAT,
    method VARCHAR(30), needs_human BOOLEAN, safety_flag BOOLEAN, reason TEXT, status VARCHAR(20),
    created_at DATETIME, updated_at DATETIME, resolved_at DATETIME
)"""
WEEK7_COLUMNS = {"tickets.assigned_to", "tickets.first_response_at", "tickets.escalation_level",
                 "tickets.escalated_at"}


def _week6_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'week6.db'}")
    with engine.begin() as conn:
        conn.execute(text(WEEK6_TICKETS))
        conn.execute(text(
            "INSERT INTO tickets (reference, message, channel, category, urgency, language, routed_role, "
            "confidence, method, needs_human, safety_flag, reason, status, created_at, updated_at) VALUES "
            "('SC-20260105-0001', 'Old message', 'web', 'academic', 'low', 'en', 'class_teacher', 0.5, "
            "'rules', 0, 0, '', 'new', '2026-01-05 08:00:00', '2026-01-05 08:00:00')"))
    return engine


def test_migrate_adds_missing_columns_and_keeps_data(tmp_path):
    engine = _week6_database(tmp_path)
    added = migrate(engine)
    assert set(added) == WEEK7_COLUMNS
    columns = {c["name"] for c in inspect(engine).get_columns("tickets")}
    assert {"assigned_to", "first_response_at", "escalation_level", "escalated_at"} <= columns
    with engine.connect() as conn:
        row = conn.execute(text("SELECT reference, escalation_level, assigned_to FROM tickets")).one()
    assert row == ("SC-20260105-0001", 0, None)     # old row kept; default filled in


def test_migrate_is_idempotent(tmp_path):
    engine = _week6_database(tmp_path)
    assert migrate(engine)
    assert migrate(engine) == []        # second run changes nothing


def test_init_db_creates_new_tables_and_migrates(tmp_path):
    engine = _week6_database(tmp_path)
    init_db(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"tickets", "staff", "staff_sessions", "ticket_events", "responses", "ai_audit_log"} <= tables
    assert migrate(engine) == []


def test_add_column_sql_works_for_sqlite_and_postgres():
    col = Ticket.__table__.c
    assert add_column_sql("tickets", col.escalation_level, sqlite.dialect()) == \
        "ALTER TABLE tickets ADD COLUMN escalation_level INTEGER DEFAULT 0"
    assert add_column_sql("tickets", col.first_response_at, postgresql.dialect()) == \
        "ALTER TABLE tickets ADD COLUMN first_response_at TIMESTAMP WITH TIME ZONE"


# ---- Events ---------------------------------------------------------------
def _ticket(client, message="Please send me the fee statement"):
    r = client.post("/tickets", json={"message": message})
    assert r.status_code == 201
    return r.json()


def test_status_changes_are_events_and_first_response_is_set_once(client):
    t = _ticket(client)
    client.patch(f"/tickets/{t['id']}/status", json={"status": "in_progress"})
    first = client.get(f"/tickets/{t['id']}").json()["first_response_at"]
    assert first
    client.patch(f"/tickets/{t['id']}/status", json={"status": "new"})
    client.patch(f"/tickets/{t['id']}/status", json={"status": "in_progress"})
    assert client.get(f"/tickets/{t['id']}").json()["first_response_at"] == first   # not moved
    evs = client.get(f"/tickets/{t['id']}/events").json()
    changes = [(e["from_value"], e["to_value"]) for e in evs if e["type"] == "status_changed"]
    assert changes == [("new", "in_progress"), ("in_progress", "new"), ("new", "in_progress")]
    assert [e["type"] for e in evs].count("first_response") == 1
    assert all(e["actor"] == "Ms Dlamini" for e in evs if e["type"] == "status_changed")


def test_approved_reply_counts_as_first_response(client):
    t = _ticket(client)
    draft = client.post(f"/tickets/{t['id']}/responses", json={"tone": "formal"}).json()
    assert client.get(f"/tickets/{t['id']}").json()["first_response_at"] is None
    client.post(f"/responses/{draft['id']}/approve", json={})
    assert client.get(f"/tickets/{t['id']}").json()["first_response_at"]


def test_reassign_is_logged_and_gives_access(client, login_as):
    t = _ticket(client, "When is the exam timetable out?")        # routed to class_teacher
    clerk, clerk_headers = login_as("admin_clerk", "Mr Khumalo")
    assert client.get(f"/tickets/{t['id']}", headers=clerk_headers).status_code == 404
    r = client.post(f"/tickets/{t['id']}/assign", json={"staff_id": clerk.id, "reason": "admin query"})
    assert r.status_code == 200 and r.json()["assigned_to"] == clerk.id
    assert client.get(f"/tickets/{t['id']}", headers=clerk_headers).status_code == 200   # now theirs
    evs = client.get(f"/tickets/{t['id']}/events").json()
    event = [e for e in evs if e["type"] == "reassigned"][-1]
    assert "Mr Khumalo" in event["to_value"] and event["actor"] == "Ms Dlamini"
    assert evs[-1]["type"] == "notified" and evs[-1]["from_value"] == "staff_assigned"   # new owner told
    assert client.post(f"/tickets/{t['id']}/assign", json={"staff_id": clerk.id}).status_code == 409   # already


def test_welfare_ticket_cannot_be_assigned_to_a_clerk(client, login_as):
    t = _ticket(client, "My daughter is being bullied")
    clerk, _ = login_as("admin_clerk")
    deputy, _ = login_as("deputy_principal")
    r = client.post(f"/tickets/{t['id']}/assign", json={"staff_id": clerk.id})
    assert r.status_code == 409 and "welfare" in r.json()["detail"]
    assert client.post(f"/tickets/{t['id']}/assign", json={"staff_id": deputy.id}).status_code == 200
    assert client.post(f"/tickets/{t['id']}/assign", json={"staff_id": 999}).status_code == 404


def test_staff_list_needs_login(client, anon_client):
    assert anon_client.get("/staff").status_code == 401
    names = [s["name"] for s in client.get("/staff").json()]
    assert names == ["Ms Dlamini"]
