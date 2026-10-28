"""Ticket events: a timeline of what happened to each ticket and who did it.

Types used:
    assigned, reassigned, unassigned   who owns the ticket
    status_changed                     new -> in_progress -> resolved
    first_response                     the school's first response (stops the response-time clock)
    escalated, critical_alert          automatic escalation (see workflow/escalation.py)
    notified                           a message was put in the outbox (to_value = recipient kind)
    fee_exemption                      a step in the fee exemption workflow

AI decisions stay in ai_audit_log (Week 6); events are about the workflow. Events never
contain the message text or a parent's details.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ticket, TicketEvent

SYSTEM = "system"   # actor for automatic actions


def log(db: Session, ticket_id: int, type: str, from_value: str | None = None,
        to_value: str | None = None, actor: str | None = None, at: datetime | None = None) -> TicketEvent:
    """Add an event. The caller commits (so an event is saved together with the change it describes)."""
    event = TicketEvent(ticket_id=ticket_id, type=type, from_value=from_value, to_value=to_value,
                        actor=actor or SYSTEM, created_at=at or datetime.now(timezone.utc))
    db.add(event)
    return event


def mark_first_response(db: Session, ticket: Ticket, actor: str | None, at: datetime) -> bool:
    """Record the first response once. Returns True if this was the first one."""
    if ticket.first_response_at is not None:
        return False
    ticket.first_response_at = at
    log(db, ticket.id, "first_response", None, None, actor, at=at)
    return True


def for_ticket(db: Session, ticket_id: int) -> list[TicketEvent]:
    query = select(TicketEvent).where(TicketEvent.ticket_id == ticket_id).order_by(TicketEvent.id)
    return list(db.scalars(query))


def exists(db: Session, ticket_id: int, type: str, to_value: str | None = None) -> bool:
    """Has this event already happened? Used to make automatic jobs idempotent."""
    query = select(TicketEvent.id).where(TicketEvent.ticket_id == ticket_id, TicketEvent.type == type)
    if to_value is not None:
        query = query.where(TicketEvent.to_value == to_value)
    return db.scalar(query.limit(1)) is not None
