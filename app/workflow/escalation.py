"""Automatic escalation, run by a scheduler calling POST /jobs/escalate (Week 8: GitHub Actions,
every 15 minutes in school hours, see .github/workflows/jobs.yml).

For every open ticket nobody has acknowledged yet:
1. Critical and still unacknowledged after 30 minutes -> alert BOTH the deputy principal and
   the principal (once per ticket).
2. First-response target missed -> move it ONE level up the escalation chain
   (config/workflow.yaml), assign it to the least-loaded person in that role, notify them, and
   log an event + an audit row. The target clock restarts for the new owner.

Idempotent: a second run at the same moment finds nothing new, because the escalated ticket
now has a fresh deadline (from escalated_at) and the critical alert is only sent once.
Fast and single-threaded: one query plus a little work per open ticket, no background threads
(it must finish inside one short HTTP request on Render's free 0.1 CPU instance).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.models import Staff, Ticket
from app.notify import messages, outbox
from app.taxonomy import ACCOUNT_ROLES, PRINCIPAL_ROLE, SENIOR_ROLES
from app.workflow import events
from app.workflow.assignment import active_staff, pick_least_loaded, staff_label
from app.workflow.sla import aware, due_text, load_workflow, sla_status

MAX_TICKETS_PER_RUN = 500


def owner_role(db: Session, ticket: Ticket) -> str:
    """The role that currently owns the ticket: the assignee's role, else the queue it is in."""
    if ticket.assigned_to:
        staff = db.get(Staff, ticket.assigned_to)
        if staff is not None:
            return staff.role
    return ticket.routed_role


def _alert_critical_unacknowledged(db: Session, ticket: Ticket, now: datetime) -> bool:
    minutes = load_workflow()["critical_acknowledge_minutes"]
    if ticket.urgency != "critical" or now - aware(ticket.created_at) < timedelta(minutes=minutes):
        return False
    if events.exists(db, ticket.id, "critical_alert"):
        return False
    told = []
    for role in SENIOR_ROLES:
        for staff in active_staff(db, role):
            outbox.notify_staff(db, staff, *messages.staff_alert(ticket, "critical_unacknowledged"),
                                kind="staff_critical_unacknowledged", ticket_id=ticket.id)
            told.append(staff_label(staff))
    events.log(db, ticket.id, "critical_alert", f"not acknowledged after {minutes} min",
               ", ".join(told)[:200] or "no senior staff account", at=now)
    audit.record(db, "escalation", "workflow", ticket_id=ticket.id,
                 output={"type": "critical_unacknowledged", "minutes": minutes, "alerted": len(told)},
                 commit=False)
    return True


def _escalate(db: Session, ticket: Ticket, now: datetime, overdue_label: str) -> str | None:
    """Move the ticket one level up. Returns the new role, or None at the top of the chain."""
    current = owner_role(db, ticket)
    next_role = load_workflow()["escalation_chain"].get(current)
    if next_role is None:
        if not events.exists(db, ticket.id, "escalation_top", str(ticket.escalation_level)):
            events.log(db, ticket.id, "escalation_top", overdue_label, str(ticket.escalation_level), at=now)
        return None

    candidates = active_staff(db, next_role)
    if not candidates and next_role != PRINCIPAL_ROLE:
        next_role, candidates = PRINCIPAL_ROLE, active_staff(db, PRINCIPAL_ROLE)
    previous = db.get(Staff, ticket.assigned_to) if ticket.assigned_to else None
    new_owner = pick_least_loaded(db, candidates)[0] if candidates else None
    ticket.assigned_to = new_owner.id if new_owner else None
    if new_owner is None:
        ticket.routed_role = next_role          # nobody to assign: put it in that role's queue
    ticket.escalation_level += 1
    ticket.escalated_at = now
    ticket.updated_at = now

    events.log(db, ticket.id, "escalated",
               f"{ACCOUNT_ROLES.get(current, current)} {staff_label(previous) or '(queue)'}: {overdue_label}"[:200],
               staff_label(new_owner) or f"{ACCOUNT_ROLES[next_role]} queue", at=now)
    audit.record(db, "escalation", "workflow", ticket_id=ticket.id,
                 output={"type": "sla_breach", "level": ticket.escalation_level, "from_role": current,
                         "to_role": next_role, "overdue": overdue_label, "assigned": bool(new_owner)},
                 commit=False)
    if new_owner is not None:
        outbox.notify_staff(db, new_owner, *messages.staff_alert(ticket, "escalated", due_text(ticket)),
                            kind="staff_escalated", ticket_id=ticket.id)
    return next_role


def run_escalations(db: Session, now: datetime | None = None) -> dict:
    now = aware(now or datetime.now(timezone.utc))
    query = (select(Ticket).where(Ticket.status == "new", Ticket.first_response_at.is_(None))
             .order_by(Ticket.created_at).limit(MAX_TICKETS_PER_RUN))
    tickets = list(db.scalars(query))
    escalated, alerts, at_top = [], [], []
    for ticket in tickets:
        if _alert_critical_unacknowledged(db, ticket, now):
            alerts.append(ticket.reference)
        sla = sla_status(ticket, now)
        if sla.status != "overdue":
            continue
        new_role = _escalate(db, ticket, now, sla.label)
        if new_role:
            escalated.append({"reference": ticket.reference, "to_role": new_role,
                              "level": ticket.escalation_level})
        else:
            at_top.append(ticket.reference)
    db.commit()
    return {"checked": len(tickets), "escalated": escalated, "critical_alerts": alerts,
            "at_top_of_chain": at_top, "run_at": now.isoformat(timespec="seconds")}
