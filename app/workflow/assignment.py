"""Who owns a ticket. Manual reassignment (logged) and, from Week 7 step 4, auto-assignment."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.auth.access import is_welfare
from app.models import Staff, Ticket
from app.taxonomy import SENIOR_ROLES
from app.workflow import events


class AssignmentError(ValueError):
    """The assignment is not allowed (e.g. a welfare ticket to a clerk)."""


def staff_label(staff: Staff | None) -> str | None:
    """How a staff member appears in events, e.g. "Mrs Pillay (#3)"."""
    return f"{staff.name} (#{staff.id})" if staff else None


def notify_assignee(db: Session, ticket: Ticket, staff: Staff, reason: str = "assigned") -> None:
    """Email the new owner (reference, category, urgency only - see notify/messages.py)."""
    from app.notify import messages, outbox

    outbox.notify_staff(db, staff, *messages.staff_alert(ticket, reason), kind=f"staff_{reason}",
                        ticket_id=ticket.id)


def reassign(db: Session, ticket: Ticket, target: Staff, actor: Staff, reason: str | None = None,
             now: datetime | None = None) -> Ticket:
    """A person moves a ticket to someone else. Child safety: welfare tickets stay with senior staff."""
    if not target.active:
        raise AssignmentError(f"{target.name} is not an active staff member")
    if is_welfare(ticket) and target.role not in SENIOR_ROLES:
        raise AssignmentError("Learner welfare tickets can only be assigned to the deputy principal or principal")
    if ticket.assigned_to == target.id:
        raise AssignmentError(f"The ticket is already assigned to {target.name}")
    now = now or datetime.now(timezone.utc)
    previous = db.get(Staff, ticket.assigned_to) if ticket.assigned_to else None
    ticket.assigned_to = target.id
    ticket.updated_at = now
    note = staff_label(target) + (f": {reason}" if reason else "")
    events.log(db, ticket.id, "reassigned", staff_label(previous), note[:200], actor.name, at=now)
    notify_assignee(db, ticket, target)
    db.commit()
    db.refresh(ticket)
    return ticket
