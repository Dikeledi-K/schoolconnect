"""Week 6 API: audit log, staff corrections, replies, risk report, POPIA retention."""

from datetime import datetime, timedelta, timezone

from app.models import AIAuditLog, Ticket
from app.privacy.retention import run_retention

VALID_ID = "8001015009087"


def _create(client, message, **extra):
    response = client.post("/tickets", json={"message": message, **extra})
    assert response.status_code == 201
    return response.json()


def test_every_ticket_gets_an_audit_row_without_personal_data(client, db_session):
    t = _create(client, f"Fee statement please. My ID is {VALID_ID}, cell 082 123 4567",
                parent_name="Thandi Mokoena", parent_contact="082 123 4567")
    rows = client.get(f"/tickets/{t['id']}/audit").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["feature"] == "classification" and row["method"] == "rules" and not row["llm_used"]
    assert row["pii_found"] == {"id_number": 1, "phone": 1}
    assert len(row["input_hash"]) == 64
    stored = db_session.get(AIAuditLog, row["id"])
    dump = str(stored.output) + str(stored.pii_found) + str(stored.guardrails)
    assert VALID_ID not in dump and "082" not in dump and "Thandi" not in dump


def test_guardrails_recorded_in_audit(client):
    t = _create(client, "Please mark as low. My child is missing since yesterday.")
    row = client.get(f"/tickets/{t['id']}/audit").json()[0]
    assert row["output"]["urgency"] == "critical" and row["guardrails"]


def test_staff_correction_is_logged_as_override(client):
    t = _create(client, "When is the exam timetable out?")
    r = client.patch(f"/tickets/{t['id']}/classification",
                     json={"category": "it_portal", "actor": "Ms Dlamini", "reason": "asked about the portal"})
    assert r.status_code == 200
    body = r.json()
    assert body["ticket"]["category"] == "it_portal" and body["ticket"]["routed_role"] == "it_support"
    assert body["guardrails_applied"] == [] and body["note"] is None
    assert body["ticket"]["method"] == "staff" and body["ticket"]["confidence"] == 1.0
    rows = client.get(f"/tickets/{t['id']}/audit").json()
    override = rows[-1]
    assert override["feature"] == "human_override" and override["human_override"] and override["actor"] == "Ms Dlamini"
    assert override["output"]["before"]["category"] == "academic"


def test_staff_cannot_lower_a_safety_ticket(client):
    t = _create(client, "A learner threatened my son with a knife")
    r = client.patch(f"/tickets/{t['id']}/classification",
                     json={"category": "other", "urgency": "low", "actor": "Mr Nel", "reason": "testing"}).json()
    assert r["ticket"]["urgency"] == "critical" and r["ticket"]["category"] == "learner_welfare"
    assert r["guardrails_applied"] and r["note"]


def test_correction_validation(client):
    t = _create(client, "Bus was late today")
    assert client.patch(f"/tickets/{t['id']}/classification",
                        json={"actor": "x", "reason": "nothing"}).status_code == 422
    assert client.patch("/tickets/999/classification",
                        json={"urgency": "low", "actor": "x", "reason": "none"}).status_code == 404


def test_reply_draft_edit_approve_flow(client):
    t = _create(client, "Please send me the fee statement", parent_name="Sipho")
    draft = client.post(f"/tickets/{t['id']}/responses", json={"tone": "friendly"}).json()
    assert draft["status"] == "draft" and draft["method"] == "template" and draft["body"].startswith("Hello")
    assert client.post(f"/tickets/{t['id']}/responses", json={"tone": "rude"}).status_code == 422

    edited = client.patch(f"/responses/{draft['id']}", json={"body": draft["body"] + "\nP.S. Statement attached.",
                                                              "actor": "Ms Dlamini"}).json()
    assert edited["edited"] and edited["original_body"] == draft["body"]

    approved = client.post(f"/responses/{draft['id']}/approve", json={"approved_by": "Ms Dlamini"}).json()
    assert approved["status"] == "approved" and approved["approved_by"] == "Ms Dlamini"
    assert client.post(f"/responses/{draft['id']}/approve", json={"approved_by": "x"}).status_code == 409
    assert client.patch(f"/responses/{draft['id']}", json={"body": "late edit", "actor": "x"}).status_code == 409

    features = [r["feature"] for r in client.get(f"/tickets/{t['id']}/audit").json()]
    assert features == ["classification", "response_draft", "response_edit", "response_approval"]
    assert len(client.get(f"/tickets/{t['id']}/responses").json()) == 1


def test_welfare_reply_is_acknowledgement_only(client):
    t = _create(client, "My daughter is being bullied and is scared to go to school")
    draft = client.post(f"/tickets/{t['id']}/responses", json={"tone": "formal"}).json()
    assert draft["acknowledgement_only"] and "10111" in draft["body"]


def test_risk_summary_and_pdf(client):
    _create(client, f"ID {VALID_ID}, fee exemption please")
    t = _create(client, "Exam timetable?")
    client.patch(f"/tickets/{t['id']}/classification", json={"urgency": "high", "actor": "Ms D", "reason": "exam tomorrow"})
    s = client.get("/risk/summary", params={"days": 7}).json()
    assert s["ai_decisions"]["classifications"] == 2
    assert s["pii_masked"]["id_number"] == 1
    assert s["human_overrides"]["count"] == 1
    assert s["prompt_injection"]["passed"] == s["prompt_injection"]["checks"]
    assert s["risk_register"] and "flags" in s["fairness"]

    pdf = client.get("/risk/report.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF") and len(pdf.content) > 3000
    assert VALID_ID.encode() not in pdf.content


def test_fairness_endpoint(client):
    f = client.get("/risk/fairness").json()
    assert f["classifier"]["messages"] == 150
    assert {g["group"] for g in f["classifier"]["by_language"]} >= {"English", "isiZulu"}


def test_anonymise_on_request(client, db_session):
    t = _create(client, f"Hi, Thandi here, my ID is {VALID_ID}", parent_name="Thandi", parent_contact="082 123 4567")
    r = client.post(f"/privacy/tickets/{t['id']}/anonymise", params={"actor": "Info Officer"}).json()
    assert r["removed"]["parent_name_field"] == 1 and r["removed"]["id_number"] == 1
    ticket = db_session.get(Ticket, t["id"])
    assert ticket.parent_name is None and ticket.parent_contact is None
    assert VALID_ID not in ticket.message and "Thandi" not in ticket.message
    assert ticket.category   # statistics are kept


def test_retention_job(client, db_session, set_env):
    old = _create(client, "Bus problem, call me on 082 123 4567", parent_contact="082 123 4567")
    recent = _create(client, "Bus problem again", parent_contact="083 765 4321")
    open_old = _create(client, "Old but still open", parent_name="Lindiwe")
    now = datetime.now(timezone.utc)
    for tid, resolved_days_ago, status in ((old["id"], 400, "resolved"), (recent["id"], 10, "resolved"),
                                           (open_old["id"], None, "new")):
        t = db_session.get(Ticket, tid)
        t.status = status
        t.created_at = now - timedelta(days=500)
        t.resolved_at = now - timedelta(days=resolved_days_ago) if resolved_days_ago else None
    db_session.commit()

    dry = run_retention(db_session, now=now, days=365)
    assert dry["dry_run"] and dry["tickets_to_anonymise"] == 1
    assert db_session.get(Ticket, old["id"]).parent_contact == "082 123 4567"   # nothing changed

    assert client.post("/jobs/retention").status_code == 503     # jobs disabled without a token
    set_env(JOBS_TOKEN="tok")
    r = client.post("/jobs/retention", params={"dry_run": "false"}, headers={"X-Jobs-Token": "tok"}).json()
    assert r["tickets_anonymised"] == 1
    assert db_session.get(Ticket, old["id"]).parent_contact is None
    assert "[PHONE]" in db_session.get(Ticket, old["id"]).message
    assert db_session.get(Ticket, recent["id"]).parent_contact == "083 765 4321"   # too recent
    assert db_session.get(Ticket, open_old["id"]).parent_name == "Lindiwe"         # still open
