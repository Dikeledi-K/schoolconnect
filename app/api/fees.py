"""Week 7: fee exemption endpoints. 403 = wrong role, 409 = wrong state, 422 = missing reason."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.workflow import visible_ticket
from app.auth.deps import current_staff, require_roles
from app.db import get_db
from app.models import FeeExemption, Staff, Ticket
from app.schemas import ChecklistUpdate, FeeDecision, FeeExemptionOut
from app.taxonomy import PRINCIPAL_ROLE
from app.workflow import fee_exemption as fx

router = APIRouter(tags=["fee exemptions"])
FEES_STAFF = Depends(require_roles(fx.FINANCE_ROLE, PRINCIPAL_ROLE))


def _out(db: Session, fe: FeeExemption, delivery: str | None = None) -> FeeExemptionOut:
    out = FeeExemptionOut.model_validate(fe)
    ticket = db.get(Ticket, fe.ticket_id)
    out.ticket_reference = ticket.reference if ticket else None
    out.delivery_status = delivery
    return out


def _get(db: Session, exemption_id: int) -> FeeExemption:
    fe = db.get(FeeExemption, exemption_id)
    if fe is None:
        raise HTTPException(status_code=404, detail="Fee exemption request not found")
    return fe


def _run(step, *args):
    try:
        return step(*args)
    except fx.FeeWorkflowError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err))


@router.post("/tickets/{ticket_id}/fee-exemption", response_model=FeeExemptionOut, status_code=201)
def create_request(ticket_id: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    """Start a fee exemption request from a fees ticket."""
    ticket = visible_ticket(db, ticket_id, staff)
    return _out(db, _run(fx.create, db, ticket, staff))


@router.get("/fee-exemptions", response_model=list[FeeExemptionOut], dependencies=[FEES_STAFF])
def list_requests(status: str | None = Query(None, description=f"One of {fx.STATES}"),
                  db: Session = Depends(get_db)):
    query = select(FeeExemption).order_by(FeeExemption.created_at)
    if status:
        query = query.where(FeeExemption.status == status)
    return [_out(db, fe) for fe in db.scalars(query)]


@router.get("/fee-exemptions/{exemption_id}", response_model=FeeExemptionOut, dependencies=[FEES_STAFF])
def get_request(exemption_id: int, db: Session = Depends(get_db)):
    return _out(db, _get(db, exemption_id))


@router.post("/fee-exemptions/{exemption_id}/start-review", response_model=FeeExemptionOut)
def start_review(exemption_id: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    return _out(db, _run(fx.start_review, db, _get(db, exemption_id), staff))


@router.put("/fee-exemptions/{exemption_id}/checklist", response_model=FeeExemptionOut)
def update_checklist(exemption_id: int, body: ChecklistUpdate, db: Session = Depends(get_db),
                     staff: Staff = Depends(current_staff)):
    return _out(db, _run(fx.update_checklist, db, _get(db, exemption_id), staff, body.received))


@router.post("/fee-exemptions/{exemption_id}/finance-decision", response_model=FeeExemptionOut)
def finance_decision(exemption_id: int, body: FeeDecision, db: Session = Depends(get_db),
                     staff: Staff = Depends(current_staff)):
    """Finance clerk recommends approve or decline (decline needs a reason)."""
    return _out(db, _run(fx.finance_decision, db, _get(db, exemption_id), staff, body.decision, body.reason))


@router.post("/fee-exemptions/{exemption_id}/principal-decision", response_model=FeeExemptionOut)
def principal_decision(exemption_id: int, body: FeeDecision, db: Session = Depends(get_db),
                       staff: Staff = Depends(current_staff)):
    """The principal's final decision (decline needs a reason)."""
    return _out(db, _run(fx.principal_decision, db, _get(db, exemption_id), staff, body.decision, body.reason))


@router.post("/fee-exemptions/{exemption_id}/notify-parent", response_model=FeeExemptionOut)
def notify_parent(exemption_id: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    """Send the decision letter (template from school facts) through the outbox."""
    fe, delivery = _run(fx.notify_parent, db, _get(db, exemption_id), staff)
    return _out(db, fe, delivery)
