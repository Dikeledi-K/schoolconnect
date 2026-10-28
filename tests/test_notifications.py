"""Week 7: the outbox (dry run, SMTP mocked), parent notifications, POPIA-safe staff alerts."""

import smtplib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.models import Outbox, Ticket
from app.notify import messages
from app.privacy.retention import run_retention

PARENT_EMAIL = "thandi.parent@example.com"
SECRET_DETAIL = "my ex-husband Sipho Zulu took her, call 082 123 4567"


def _ticket(client, message="Please send me the fee statement", **extra):
    r = client.post("/tickets", json={"message": message, **extra})
    assert r.status_code == 201
    return r.json()


def _approve_reply(client, ticket_id):
    draft = client.post(f"/tickets/{ticket_id}/responses", json={"tone": "formal"}).json()
    r = client.post(f"/responses/{draft['id']}/approve", json={})
    assert r.status_code == 200
    return r.json()


def _rows(db_session, **filters):
    return db_session.query(Outbox).filter_by(**filters).all()


def test_dry_run_writes_to_the_outbox_and_sends_nothing(client, db_session):
    t = _ticket(client, parent_contact=PARENT_EMAIL)
    with patch("smtplib.SMTP") as smtp:
        approved = _approve_reply(client, t["id"])
    smtp.assert_not_called()
    assert approved["delivery_status"] == "dry_run"
    row = _rows(db_session, kind="parent_reply")[0]
    assert row.status == "dry_run" and row.recipient == PARENT_EMAIL and row.sent_at is None
    assert row.body == approved["body"] and t["reference"] in row.subject
    listed = client.get(f"/tickets/{t['id']}/responses").json()[0]
    assert listed["delivery_status"] == "dry_run"


def test_smtp_mode_sends_email(client, db_session, set_env):
    set_env(NOTIFY_MODE="smtp", SMTP_HOST="smtp.test.example", SMTP_PORT="2525",
            SMTP_USER="office", SMTP_PASSWORD="pw", SMTP_FROM="office@ubuntu-demo.school.example")
    t = _ticket(client, parent_contact=PARENT_EMAIL)
    with patch("smtplib.SMTP") as smtp:
        approved = _approve_reply(client, t["id"])
    smtp.assert_called_once_with("smtp.test.example", 2525, timeout=10)
    server = smtp.return_value.__enter__.return_value
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("office", "pw")
    sent = server.send_message.call_args.args[0]
    assert sent["To"] == PARENT_EMAIL and sent["From"] == "office@ubuntu-demo.school.example"
    assert approved["delivery_status"] == "sent"
    assert _rows(db_session, kind="parent_reply")[0].sent_at is not None


def test_smtp_failure_is_recorded_with_the_address_masked(client, db_session, set_env):
    set_env(NOTIFY_MODE="smtp", SMTP_HOST="smtp.test.example")
    t = _ticket(client, parent_contact=PARENT_EMAIL)
    failing = MagicMock(side_effect=smtplib.SMTPRecipientsRefused({PARENT_EMAIL: (550, b"no such user")}))
    with patch("smtplib.SMTP", failing):
        approved = _approve_reply(client, t["id"])
    assert approved["delivery_status"] == "failed"
    row = _rows(db_session, kind="parent_reply")[0]
    assert row.status == "failed" and PARENT_EMAIL not in row.error and "[EMAIL]" in row.error


def test_phone_contacts_are_not_supported_yet(client, db_session):
    t = _ticket(client, parent_contact="082 123 4567")
    assert _approve_reply(client, t["id"])["delivery_status"] == "not_supported"
    row = _rows(db_session, kind="parent_reply")[0]
    assert row.channel == "phone" and "phone the parent" in row.error
    outbox = client.get(f"/tickets/{t['id']}/outbox").json()
    assert outbox[0]["status"] == "not_supported"
    public = client.get(f"/tickets/by-reference/{t['reference']}").json()
    assert public["reply_status"] == "replied_not_emailed"


def test_no_contact_means_no_outbox_row(client, db_session):
    t = _ticket(client)
    assert _approve_reply(client, t["id"])["delivery_status"] == "no_contact"
    assert _rows(db_session, kind="parent_reply") == []


def test_parent_is_told_when_the_ticket_is_resolved(client, db_session):
    t = _ticket(client, parent_contact=PARENT_EMAIL)
    client.patch(f"/tickets/{t['id']}/status", json={"status": "resolved"})
    client.patch(f"/tickets/{t['id']}/status", json={"status": "resolved"})     # no second message
    rows = _rows(db_session, kind="parent_resolved")
    assert len(rows) == 1 and t["reference"] in rows[0].body and "010 000 0000" in rows[0].body
    events = client.get(f"/tickets/{t['id']}/events").json()
    notified = [e for e in events if e["type"] == "notified"]
    assert notified[-1]["from_value"] == "parent_resolved" and notified[-1]["to_value"] == "dry_run"
    assert PARENT_EMAIL not in str(events)          # the timeline never holds the address


def test_by_reference_reply_status_sent(client, set_env):
    set_env(NOTIFY_MODE="smtp", SMTP_HOST="smtp.test.example")
    t = _ticket(client, parent_contact=PARENT_EMAIL)
    assert client.get(f"/tickets/by-reference/{t['reference']}").json()["reply_status"] == "none"
    with patch("smtplib.SMTP"):
        _approve_reply(client, t["id"])
    public = client.get(f"/tickets/by-reference/{t['reference']}").json()
    assert public["reply_status"] == "sent" and "message" not in public and "parent_contact" not in public


# ---- POPIA: staff alerts contain no message text or personal details -------
def test_staff_assignment_alert_contains_no_message_or_pii(client, db_session, login_as):
    t = _ticket(client, f"Question about the school bus: {SECRET_DETAIL}",
                parent_name="Thandi Mokoena", parent_contact=PARENT_EMAIL)
    clerk, _ = login_as("admin_clerk", "Mr Khumalo")
    assert client.post(f"/tickets/{t['id']}/assign", json={"staff_id": clerk.id}).status_code == 200
    alert = _rows(db_session, kind="staff_assigned", recipient=clerk.email)[0]
    text = alert.subject + alert.body
    assert t["reference"] in text and "Category:" in text and "Urgency:" in text
    for secret in ("Sipho", "082 123 4567", "ex-husband", "Thandi", PARENT_EMAIL, "school bus"):
        assert secret not in text


def test_welfare_alert_says_only_the_reference(db_session):
    ticket = Ticket(reference="SC-20260302-0001", message=SECRET_DETAIL, category="learner_welfare",
                    urgency="critical", safety_flag=True)
    subject, body = messages.staff_alert(ticket, "assigned", due_text="Mon 02 Mar 10:00")
    assert body == "New learner welfare ticket SC-20260302-0001, open SchoolConnect."
    assert "critical" not in (subject + body).lower() and "Mar" not in body
    _, escalated = messages.staff_alert(ticket, "escalated")
    assert escalated == "Escalated learner welfare ticket SC-20260302-0001, open SchoolConnect."


def test_retention_also_anonymises_outbox_rows(client, db_session, set_env):
    t = _ticket(client, "Bus problem, my name is Thandi", parent_name="Thandi", parent_contact=PARENT_EMAIL)
    _approve_reply(client, t["id"])
    client.patch(f"/tickets/{t['id']}/status", json={"status": "resolved"})
    ticket = db_session.get(Ticket, t["id"])
    ticket.resolved_at = datetime.now(timezone.utc) - timedelta(days=400)
    db_session.commit()
    rows = [r for r in _rows(db_session, ticket_id=t["id"]) if r.kind.startswith("parent_")]
    assert len(rows) == 2 and all(r.recipient == PARENT_EMAIL for r in rows)

    run_retention(db_session, days=365, dry_run=False)
    for row in rows:
        db_session.refresh(row)
        assert row.recipient == "[REMOVED]" and "Thandi" not in row.body
    assert db_session.get(Ticket, t["id"]).parent_contact is None
