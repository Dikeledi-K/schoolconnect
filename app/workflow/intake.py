"""The ONE path every new parent message takes, whatever channel it came in on.

    web form (POST /tickets)  ─┐
    email / WhatsApp webhook  ─┴─> intake_ticket():
        1. classify (only the message text; Week 6: masked before any AI sees it)
        2. save the ticket
        3. audit row for the AI decision (masked input hash, PII counts, guardrails)
        4. auto-assign to the least-loaded person in the right role
        5. notify the assignee, and the senior staff if it is critical
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import audit, crud
from app.classifier import classify_message
from app.config import get_settings
from app.llm_text import llm_available, model_name
from app.models import Ticket
from app.privacy.pii import mask_pii
from app.schemas import TicketCreate
from app.workflow.assignment import alert_seniors_of_new_critical, auto_assign


def intake_ticket(db: Session, body: TicketCreate) -> Ticket:
    # Only the message text goes to the classifier, never name/contact. Week 6: the text is also
    # masked (IDs, phones, emails, the parent's own name) before any AI sees it.
    names = [body.parent_name] if body.parent_name else None
    settings = get_settings()
    result = classify_message(body.message, names=names)
    ticket = crud.create_ticket(db, body, result)
    masked = mask_pii(body.message, names)
    ai_configured = llm_available(settings)
    audit.record(
        db, "classification", result.method, ticket_id=ticket.id,
        model=model_name(settings) if result.method != "rules" else None,
        llm_used=result.method != "rules",
        fallback_reason="AI failed or gave invalid output" if ai_configured and result.method == "rules" else None,
        masked_input=masked.text, pii_found=masked.counts, guardrails=result.guardrails_applied,
        output={"category": result.category, "urgency": result.urgency, "language": result.language,
                "confidence": result.confidence, "needs_human": result.needs_human,
                "safety_flag": result.safety_flag},
    )
    assignee = auto_assign(db, ticket)
    alert_seniors_of_new_critical(db, ticket, assignee)
    db.commit()
    db.refresh(ticket)
    return ticket
