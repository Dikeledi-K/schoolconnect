"""Who owns a ticket: automatic assignment when it arrives, and manual reassignment.

Auto-assignment (same workload model as Week 5, config/workload.yaml):
1. Learner-welfare and critical tickets always go to the deputy principal
   (or the principal if there is no active deputy).
2. Other tickets go to an active staff member in the ticket's routed role.
3. Among those, pick the person with the LEAST OPEN WORK, measured in hours:
   the handling minutes of every open ticket they hold, added up.
4. A tie is broken by fewest assignments in total, then by staff id (so it is predictable).
5. Nobody active in that role? The ticket stays in the role queue and the reason is logged.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.access import is_welfare
from app.forecasting.workload import load_workload
from app.models import Staff, Ticket
from app.taxonomy import ACCOUNT_ROLES, PRINCIPAL_ROLE, SENIOR_ROLES
from app.workflow import events


class AssignmentError(ValueError):
    """The assignment is not allowed (e.g. a welfare ticket to a clerk)."""


def staff_label(staff: Staff | None) -> str | None:
    """How a staff member appears in events, e.g. "Mrs Pillay (#3)"."""
    return f"{staff.name} (#{staff.id})" if staff else None


def open_hours(db: Session, staff_id: int, handling_minutes: dict | None = None) -> float:
    """Hours of work in this person's open tickets (new or in progress)."""
    minutes = handling_minutes or load_workload()["handling_minutes"]
    rows = db.execute(select(Ticket.category, func.count()).where(
        Ticket.assigned_to == staff_id, Ticket.status != "resolved").group_by(Ticket.category)).all()
    return sum(minutes.get(category, 0) * n for category, n in rows) / 60


def total_assignments(db: Session, staff_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Ticket).where(Ticket.assigned_to == staff_id)) or 0


def active_staff(db: Session, role: str) -> list[Staff]:
    return list(db.scalars(select(Staff).where(Staff.role == role, Staff.active.is_(True)).order_by(Staff.id)))


def target_role(ticket: Ticket) -> str:
    """Which role should own the ticket. Child safety first."""
    if is_welfare(ticket) or ticket.urgency == "critical":
        return "deputy_principal"
    return ticket.routed_role


def pick_least_loaded(db: Session, candidates: list[Staff]) -> tuple[Staff, float]:
    minutes = load_workload()["handling_minutes"]
    scored = [(open_hours(db, s.id, minutes), total_assignments(db, s.id), s.id, s) for s in candidates]
    hours, _, _, chosen = min(scored, key=lambda row: row[:3])
    return chosen, hours


def auto_assign(db: Session, ticket: Ticket, now: datetime | None = None) -> Staff | None:
    """Assign a new ticket (see the rules at the top). The caller commits."""
    now = now or datetime.now(timezone.utc)
    role = target_role(ticket)
    candidates = active_staff(db, role)
    if not candidates and role == "deputy_principal":
        role, candidates = PRINCIPAL_ROLE, active_staff(db, PRINCIPAL_ROLE)
    if not candidates:
        events.log(db, ticket.id, "unassigned", None,
                   f"No active {ACCOUNT_ROLES[role]}: waiting in the {ACCOUNT_ROLES[role]} queue", at=now)
        return None
    chosen, hours = pick_least_loaded(db, candidates)
    ticket.assigned_to = chosen.id
    events.log(db, ticket.id, "assigned", f"auto: least open work ({hours:.1f} h)", staff_label(chosen), at=now)
    notify_assignee(db, ticket, chosen)
    return chosen


def alert_seniors_of_new_critical(db: Session, ticket: Ticket, assignee: Staff | None) -> None:
    """A new critical ticket: the deputy principal(s) and principal(s) all hear about it at once."""
    from app.notify import messages, outbox

    if ticket.urgency != "critical":
        return
    for role in SENIOR_ROLES:
        for staff in active_staff(db, role):
            if assignee is None or staff.id != assignee.id:      # the assignee already got an alert
                outbox.notify_staff(db, staff, *messages.staff_alert(ticket, "new_critical"),
                                    kind="staff_new_critical", ticket_id=ticket.id)


def notify_assignee(db: Session, ticket: Ticket, staff: Staff, reason: str = "assigned") -> None:
    """Email the new owner (reference, category, urgency only - see notify/messages.py)."""
    from app.notify import messages, outbox
    from app.workflow.sla import due_text

    outbox.notify_staff(db, staff, *messages.staff_alert(ticket, reason, due_text(ticket)),
                        kind=f"staff_{reason}", ticket_id=ticket.id)


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
