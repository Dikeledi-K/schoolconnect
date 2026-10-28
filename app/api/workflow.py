"""Week 7: workflow endpoints for logged-in staff (staff list, ticket timeline, reassignment)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud
from app.auth.access import can_see_ticket
from app.auth.deps import current_staff
from app.db import get_db
from app.models import Staff
from app.schemas import AssignRequest, StaffOut, TicketEventOut, TicketOut
from app.workflow import assignment, events

router = APIRouter(tags=["workflow"])


def visible_ticket(db: Session, ticket_id: int, staff: Staff):
    """The ticket, or 404 if it does not exist OR this person may not see it."""
    ticket = crud.get_ticket(db, ticket_id)
    if ticket is None or not can_see_ticket(staff, ticket):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.get("/staff", response_model=list[StaffOut])
def list_staff(db: Session = Depends(get_db), _: Staff = Depends(current_staff)):
    """Colleagues, e.g. for the "reassign to" list."""
    return list(db.scalars(select(Staff).order_by(Staff.role, Staff.name)))


@router.get("/tickets/{ticket_id}/events", response_model=list[TicketEventOut])
def ticket_events(ticket_id: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    """The ticket's timeline: assignments, status changes, escalations, notifications."""
    visible_ticket(db, ticket_id, staff)
    return events.for_ticket(db, ticket_id)


@router.post("/tickets/{ticket_id}/assign", response_model=TicketOut)
def assign_ticket(ticket_id: int, body: AssignRequest, db: Session = Depends(get_db),
                  staff: Staff = Depends(current_staff)):
    """Reassign a ticket to a colleague (logged as an event)."""
    ticket = visible_ticket(db, ticket_id, staff)
    target = db.get(Staff, body.staff_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Staff member not found")
    try:
        return assignment.reassign(db, ticket, target, staff, body.reason)
    except assignment.AssignmentError as err:
        raise HTTPException(status_code=409, detail=str(err))
