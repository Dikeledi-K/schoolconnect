"""Week 7: fee exemption state machine. Every transition, valid and invalid; roles; reasons; letters."""

import pytest

from app.models import AIAuditLog, Outbox
from app.responses.templates import load_school_info
from app.workflow.fee_exemption import STATES

PARENT = "parent.fees@example.com"
DOCS = len(load_school_info()["fees"]["exemption_documents"])


@pytest.fixture
def setup(client, login_as):
    """A fees ticket, a finance clerk, a class teacher, and the principal (`client`)."""
    _, finance = login_as("finance_clerk", "Mrs Pillay")
    _, teacher = login_as("class_teacher", "Mr Nel")
    ticket = client.post("/tickets", json={"message": "I lost my job, how do I apply for a fee exemption?",
                                           "parent_contact": PARENT}).json()
    return {"ticket": ticket, "finance": finance, "teacher": teacher, "principal": {}}


def _create(client, setup):
    r = client.post(f"/tickets/{setup['ticket']['id']}/fee-exemption", headers=setup["finance"])
    assert r.status_code == 201, r.text
    return r.json()


# step name -> (who does it, how)
def _step(client, setup, fe_id, step):
    f, p = setup["finance"], setup["principal"]
    if step == "start":
        return client.post(f"/fee-exemptions/{fe_id}/start-review", headers=f)
    if step == "checklist":
        return client.put(f"/fee-exemptions/{fe_id}/checklist", headers=f, json={"received": [True] * DOCS})
    if step == "finance":
        return client.post(f"/fee-exemptions/{fe_id}/finance-decision", headers=f,
                           json={"decision": "decline", "reason": "Income above the threshold"})
    if step == "principal":
        return client.post(f"/fee-exemptions/{fe_id}/principal-decision", headers=p, json={"decision": "approve"})
    if step == "notify":
        return client.post(f"/fee-exemptions/{fe_id}/notify-parent", headers=f)
    raise ValueError(step)


PATH = {"submitted": [], "finance_review": ["start"], "principal_decision": ["start", "finance"],
        "approved": ["start", "finance", "principal"], "parent_notified": ["start", "finance", "principal", "notify"]}
VALID = {("submitted", "start"), ("finance_review", "checklist"), ("finance_review", "finance"),
         ("principal_decision", "principal"), ("approved", "notify"), ("declined", "notify")}


def _advance(client, setup, to):
    fe = _create(client, setup)
    if to == "declined":
        for step in ["start", "finance"]:
            assert _step(client, setup, fe["id"], step).status_code == 200
        r = client.post(f"/fee-exemptions/{fe['id']}/principal-decision",
                        json={"decision": "decline", "reason": "Income above the threshold"})
        assert r.status_code == 200
        return r.json()
    for step in PATH[to]:
        r = _step(client, setup, fe["id"], step)
        assert r.status_code == 200, (step, r.text)
    return client.get(f"/fee-exemptions/{fe['id']}").json()


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("step", ["start", "checklist", "finance", "principal", "notify"])
def test_every_transition(client, setup, state, step):
    fe = _advance(client, setup, state)
    assert fe["status"] == state
    r = _step(client, setup, fe["id"], step)
    if (state, step) in VALID:
        assert r.status_code == 200, r.text
    else:
        assert r.status_code == 409, (state, step, r.text)
        assert client.get(f"/fee-exemptions/{fe['id']}").json()["status"] == state   # unchanged


def test_full_approval_flow_logs_every_step_and_notifies_the_parent(client, setup, db_session):
    fe = _create(client, setup)
    assert fe["status"] == "submitted" and len(fe["checklist"]) == DOCS
    assert not any(item["received"] for item in fe["checklist"])
    f = setup["finance"]
    client.post(f"/fee-exemptions/{fe['id']}/start-review", headers=f)
    client.put(f"/fee-exemptions/{fe['id']}/checklist", headers=f, json={"received": [True] * DOCS})
    client.post(f"/fee-exemptions/{fe['id']}/finance-decision", headers=f, json={"decision": "approve"})
    client.post(f"/fee-exemptions/{fe['id']}/principal-decision", json={"decision": "approve"})
    done = client.post(f"/fee-exemptions/{fe['id']}/notify-parent").json()
    assert done["status"] == "parent_notified" and done["delivery_status"] == "dry_run"
    assert done["finance_by"] == "Mrs Pillay" and done["principal_by"] == "Ms Dlamini"

    tid = setup["ticket"]["id"]
    steps = [(e["from_value"], e["to_value"]) for e in client.get(f"/tickets/{tid}/events").json()
             if e["type"] == "fee_exemption"]
    assert steps == [(None, "submitted"), ("submitted", "finance_review"), ("finance_review", "principal_decision"),
                     ("principal_decision", "approved"), ("approved", "parent_notified")]
    audit_rows = db_session.query(AIAuditLog).filter_by(ticket_id=tid, feature="fee_exemption").all()
    assert len(audit_rows) == 6        # 5 steps + the checklist update
    letter = db_session.query(Outbox).filter_by(ticket_id=tid, kind="parent_fee_decision").one()
    assert letter.recipient == PARENT and "has been approved" in letter.body
    assert load_school_info()["school"]["phone"] in letter.body and setup["ticket"]["reference"] in letter.body


def test_decline_needs_a_reason_and_the_reason_reaches_the_parent(client, setup, db_session):
    fe = _advance(client, setup, "finance_review")
    f = setup["finance"]
    assert client.post(f"/fee-exemptions/{fe['id']}/finance-decision", headers=f,
                       json={"decision": "decline"}).status_code == 422
    assert client.post(f"/fee-exemptions/{fe['id']}/finance-decision", headers=f,
                       json={"decision": "decline", "reason": "Payslips show income above the limit"}).status_code == 200
    assert client.post(f"/fee-exemptions/{fe['id']}/principal-decision",
                       json={"decision": "decline", "reason": "  "}).status_code == 422
    r = client.post(f"/fee-exemptions/{fe['id']}/principal-decision",
                    json={"decision": "decline", "reason": "Household income is above the exemption limit"})
    assert r.json()["status"] == "declined" and r.json()["finance_note"] == "Payslips show income above the limit"
    client.post(f"/fee-exemptions/{fe['id']}/notify-parent", headers=f)
    letter = db_session.query(Outbox).filter_by(kind="parent_fee_decision").one()
    assert "was not approved" in letter.body and "Reason: Household income is above the exemption limit" in letter.body


def test_approval_needs_every_document_ticked(client, setup):
    fe = _advance(client, setup, "finance_review")
    f = setup["finance"]
    client.put(f"/fee-exemptions/{fe['id']}/checklist", headers=f, json={"received": [True] * (DOCS - 1) + [False]})
    r = client.post(f"/fee-exemptions/{fe['id']}/finance-decision", headers=f, json={"decision": "approve"})
    assert r.status_code == 409 and "document" in r.json()["detail"]
    assert client.put(f"/fee-exemptions/{fe['id']}/checklist", headers=f,
                      json={"received": [True]}).status_code == 422          # wrong number of ticks


@pytest.mark.parametrize("who,step", [
    ("principal", "start"), ("teacher", "start"),            # finance steps: finance clerk only
    ("principal", "checklist"), ("principal", "finance"),
    ("finance", "principal"), ("teacher", "principal"),      # final decision: principal only
    ("teacher", "notify"),
])
def test_wrong_role_gets_403(client, setup, who, step):
    state = {"start": "submitted", "checklist": "finance_review", "finance": "finance_review",
             "principal": "principal_decision", "notify": "approved"}[step]
    fe = _advance(client, setup, state)
    swapped = {**setup, "finance": setup[who], "principal": setup[who]}
    assert _step(client, swapped, fe["id"], step).status_code == 403


def test_only_finance_and_principal_see_the_queue(client, setup):
    _create(client, setup)
    assert client.get("/fee-exemptions", headers=setup["teacher"]).status_code == 403
    assert len(client.get("/fee-exemptions", headers=setup["finance"]).json()) == 1
    assert client.get("/fee-exemptions", params={"status": "approved"}).json() == []


def test_create_rules(client, setup):
    _create(client, setup)
    assert client.post(f"/tickets/{setup['ticket']['id']}/fee-exemption").status_code == 409   # one per ticket
    other = client.post("/tickets", json={"message": "When is the exam timetable out?"}).json()
    r = client.post(f"/tickets/{other['id']}/fee-exemption")
    assert r.status_code == 409 and "fees ticket" in r.json()["detail"]
    assert client.post(f"/tickets/{other['id']}/fee-exemption", headers=setup["finance"]).status_code == 404
