"""Fee exemption approval: a strict state machine. No step can be skipped.

    submitted ──start review (finance clerk)──> finance_review
    finance_review ──recommend approve/decline (finance clerk)──> principal_decision
    principal_decision ──approve/decline (principal)──> approved | declined
    approved | declined ──notify parent──> parent_notified

Rules:
- Only the finance clerk does the finance steps; only the principal makes the final decision.
- The finance clerk ticks off the documents from config/school_info.yaml (fees.exemption_documents).
  Recommending approval needs every document; recommending a decline needs a reason.
- A final decline needs a reason (it is included in the letter to the parent).
- The parent letter is a fixed template built from school facts only (no AI).
- Every step is a ticket event AND an audit row (who, when, from which state to which).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.models import FeeExemption, Staff, Ticket
from app.responses.templates import load_school_info
from app.taxonomy import PRINCIPAL_ROLE
from app.workflow import events

FINANCE_ROLE = "finance_clerk"
FEES_CATEGORY = "fees_exemptions"
STATES = ["submitted", "finance_review", "principal_decision", "approved", "declined", "parent_notified"]


class FeeWorkflowError(Exception):
    """status_code: 403 wrong role, 409 wrong state, 422 missing information."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def _require_role(staff: Staff, *roles: str) -> None:
    if staff.role not in roles:
        names = " or ".join(r.replace("_", " ") for r in roles)
        raise FeeWorkflowError(f"Only the {names} can do this step", 403)


def _require_state(fe: FeeExemption, *states: str) -> None:
    if fe.status not in states:
        raise FeeWorkflowError(f"This request is '{fe.status}'; this step needs '{' or '.join(states)}'", 409)


def _move(db: Session, fe: FeeExemption, to: str, staff: Staff, **details) -> FeeExemption:
    """Change state, and log it as a ticket event and an audit row, in one commit."""
    before = fe.status
    fe.status = to
    events.log(db, fe.ticket_id, "fee_exemption", before, to, staff.name)
    audit.record(db, "fee_exemption", "staff", ticket_id=fe.ticket_id, actor=staff.name, human_override=True,
                 output={"exemption_id": fe.id, "from": before, "to": to, **details}, commit=False)
    db.commit()
    db.refresh(fe)
    return fe


def _notify_role(db: Session, fe: FeeExemption, role: str, text: str) -> None:
    """Tell the next person a request is waiting (reference only, no personal details)."""
    from app.notify import outbox
    from app.workflow.assignment import active_staff

    ticket = db.get(Ticket, fe.ticket_id)
    for staff in active_staff(db, role):
        outbox.notify_staff(db, staff, f"SchoolConnect: fee exemption {ticket.reference}",
                            f"Fee exemption for ticket {ticket.reference}: {text}. Open SchoolConnect.",
                            kind="staff_fee_exemption", ticket_id=fe.ticket_id)


# --------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------
def create(db: Session, ticket: Ticket, staff: Staff) -> FeeExemption:
    if ticket.category != FEES_CATEGORY:
        raise FeeWorkflowError("Fee exemptions can only be started from a fees ticket", 409)
    if db.scalar(select(FeeExemption).where(FeeExemption.ticket_id == ticket.id)):
        raise FeeWorkflowError("This ticket already has a fee exemption request", 409)
    documents = load_school_info()["fees"]["exemption_documents"]
    fe = FeeExemption(ticket_id=ticket.id, status="submitted",
                      checklist=[{"document": d, "received": False} for d in documents])
    db.add(fe)
    db.flush()
    events.log(db, ticket.id, "fee_exemption", None, "submitted", staff.name)
    audit.record(db, "fee_exemption", "staff", ticket_id=ticket.id, actor=staff.name, human_override=True,
                 output={"exemption_id": fe.id, "from": None, "to": "submitted"}, commit=False)
    _notify_role(db, fe, FINANCE_ROLE, "new request to review")
    db.commit()
    db.refresh(fe)
    return fe


def start_review(db: Session, fe: FeeExemption, staff: Staff) -> FeeExemption:
    _require_role(staff, FINANCE_ROLE)
    _require_state(fe, "submitted")
    return _move(db, fe, "finance_review", staff)


def update_checklist(db: Session, fe: FeeExemption, staff: Staff, received: list[bool]) -> FeeExemption:
    _require_role(staff, FINANCE_ROLE)
    _require_state(fe, "finance_review")
    if len(received) != len(fe.checklist):
        raise FeeWorkflowError(f"Give one tick per document ({len(fe.checklist)} documents)", 422)
    # Assign a NEW list so SQLAlchemy notices the JSON change.
    fe.checklist = [{"document": item["document"], "received": bool(tick)}
                    for item, tick in zip(fe.checklist, received)]
    audit.record(db, "fee_exemption", "staff", ticket_id=fe.ticket_id, actor=staff.name, human_override=True,
                 output={"exemption_id": fe.id, "checklist": [i["received"] for i in fe.checklist]}, commit=False)
    db.commit()
    db.refresh(fe)
    return fe


def finance_decision(db: Session, fe: FeeExemption, staff: Staff, decision: str,
                     reason: str | None) -> FeeExemption:
    _require_role(staff, FINANCE_ROLE)
    _require_state(fe, "finance_review")
    if decision == "approve" and not all(item["received"] for item in fe.checklist):
        raise FeeWorkflowError("Tick every document before recommending approval", 409)
    if decision == "decline" and not (reason or "").strip():
        raise FeeWorkflowError("A reason is needed to recommend a decline", 422)
    fe.finance_decision, fe.finance_by, fe.finance_at = decision, staff.name, datetime.now(timezone.utc)
    fe.finance_note = (reason or "").strip() or None
    _notify_role(db, fe, PRINCIPAL_ROLE, f"finance recommends: {decision}; waiting for your decision")
    return _move(db, fe, "principal_decision", staff, recommendation=decision)


def principal_decision(db: Session, fe: FeeExemption, staff: Staff, decision: str,
                       reason: str | None) -> FeeExemption:
    _require_role(staff, PRINCIPAL_ROLE)
    _require_state(fe, "principal_decision")
    if decision == "decline" and not (reason or "").strip():
        raise FeeWorkflowError("A reason is needed to decline (it is sent to the parent)", 422)
    fe.principal_decision, fe.principal_by, fe.principal_at = decision, staff.name, datetime.now(timezone.utc)
    fe.decline_reason = reason.strip() if decision == "decline" else None
    return _move(db, fe, "approved" if decision == "approve" else "declined", staff, decision=decision,
                 followed_recommendation=decision == fe.finance_decision)


def parent_letter(fe: FeeExemption, ticket: Ticket, info: dict | None = None) -> tuple[str, str]:
    """The letter to the parent: a fixed template, facts from school_info.yaml only."""
    info = info or load_school_info()
    s = info["school"]
    if fe.status == "approved":
        outcome = "We are pleased to tell you that your application for a school fee exemption has been approved."
    else:
        outcome = ("We regret that your application for a school fee exemption was not approved.\n\n"
                   f"Reason: {fe.decline_reason}")
    body = (f"Dear Parent/Guardian,\n\n{outcome}\n\n"
            f"Your reference number is {ticket.reference}. If you have questions, please contact the office on "
            f"{s['phone']} or {s['email']} ({s['office_hours']}).\n\nKind regards,\n{s['name']} office")
    return f"Fee exemption decision ({ticket.reference})", body


def notify_parent(db: Session, fe: FeeExemption, staff: Staff) -> tuple[FeeExemption, str]:
    """Send the decision letter. Returns the request and the delivery status."""
    from app.notify import outbox

    _require_role(staff, FINANCE_ROLE, PRINCIPAL_ROLE)
    _require_state(fe, "approved", "declined")
    ticket = db.get(Ticket, fe.ticket_id)
    row = outbox.notify_parent(db, ticket, *parent_letter(fe, ticket), kind="parent_fee_decision")
    delivery = row.status if row else "no_contact"
    return _move(db, fe, "parent_notified", staff, decision=fe.status, delivery=delivery), delivery
