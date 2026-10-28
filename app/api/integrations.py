"""Week 7: POST /integrations/inbound-message - other systems create tickets (signed webhook)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.integrations.inbound import InboundAuthError, verify
from app.schemas import InboundMessage, InboundResult, TicketCreate
from app.workflow.intake import intake_ticket

router = APIRouter(prefix="/integrations", tags=["integrations"])


async def verified_body(request: Request, x_timestamp: str | None = Header(default=None),
                        x_signature: str | None = Header(default=None)) -> bytes:
    """Read the RAW body (the signature is over the exact bytes) and check the signature."""
    secret = get_settings().inbound_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Inbound integrations are disabled (INBOUND_SECRET not set)")
    body = await request.body()
    try:
        verify(secret, x_timestamp, x_signature, body)
    except InboundAuthError as err:
        raise HTTPException(status_code=401, detail=str(err))
    return body


@router.post("/inbound-message", response_model=InboundResult, status_code=201)
def inbound_message(body: bytes = Depends(verified_body), db: Session = Depends(get_db)) -> InboundResult:
    """A message from an email forwarder or WhatsApp gateway. Same path as the web form:
    masking, classification, guardrails, audit, auto-assignment, notifications."""
    try:
        msg = InboundMessage.model_validate_json(body)
        data = TicketCreate(message=msg.message, parent_name=msg.sender_name, parent_contact=msg.sender_contact,
                            learner_grade=msg.learner_grade, channel=msg.channel)
    except ValidationError as err:
        raise HTTPException(status_code=422, detail=err.errors(include_url=False, include_input=False, include_context=False))
    ticket = intake_ticket(db, data)
    return InboundResult(reference=ticket.reference, channel=ticket.channel, category=ticket.category,
                         urgency=ticket.urgency, assigned=ticket.assigned_to is not None)
