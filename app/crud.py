"""Database reads and writes. No HTTP here, so these are easy to test and reuse in scripts."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Ticket, utcnow
from app.schemas import ClassificationResult, TicketCreate
from app.taxonomy import CATEGORIES, LANGUAGES, STATUSES, URGENCY_LEVELS


def generate_reference(db: Session, when: datetime) -> str:
    """Next reference for that day: SC-YYYYMMDD-0001, SC-YYYYMMDD-0002, ...

    We look at the highest number already used that day and add one.
    The `reference` column is UNIQUE, so a clash would raise rather than duplicate.
    """
    prefix = f"SC-{when:%Y%m%d}-"
    last = db.scalar(
        select(func.max(Ticket.reference)).where(Ticket.reference.like(prefix + "%"))
    )
    number = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{number:04d}"


def create_ticket(
    db: Session,
    data: TicketCreate,
    result: ClassificationResult,
    created_at: datetime | None = None,
) -> Ticket:
    """Save a new ticket. `created_at` is only passed by the seed script (back-dated demo data)."""
    created_at = created_at or utcnow()
    ticket = Ticket(
        reference=generate_reference(db, created_at),
        message=data.message,
        parent_name=data.parent_name,
        parent_contact=data.parent_contact,
        learner_grade=data.learner_grade,
        channel=data.channel,
        category=result.category,
        urgency=result.urgency,
        language=result.language,
        routed_role=result.routed_role,
        confidence=result.confidence,
        method=result.method,
        needs_human=result.needs_human,
        safety_flag=result.safety_flag,
        reason=result.reason,
        status="new",
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def list_tickets(
    db: Session,
    status: str | None = None,
    category: str | None = None,
    urgency: str | None = None,
    language: str | None = None,
    routed_role: str | None = None,
    needs_human: bool | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
    visible=None,
) -> list[Ticket]:
    """Newest first. Every filter is optional.

    `visible` (Week 7) is the SQL rule for which tickets the logged-in staff member may see.
    """
    query = select(Ticket)
    if visible is not None:
        query = query.where(visible)
    if status:
        query = query.where(Ticket.status == status)
    if category:
        query = query.where(Ticket.category == category)
    if urgency:
        query = query.where(Ticket.urgency == urgency)
    if language:
        query = query.where(Ticket.language == language)
    if routed_role:
        query = query.where(Ticket.routed_role == routed_role)
    if needs_human is not None:
        query = query.where(Ticket.needs_human == needs_human)
    if search:
        like = f"%{search}%"
        query = query.where(or_(Ticket.message.ilike(like), Ticket.reference.ilike(like)))
    query = query.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(query))


def get_ticket(db: Session, ticket_id: int) -> Ticket | None:
    return db.get(Ticket, ticket_id)


def get_ticket_by_reference(db: Session, reference: str) -> Ticket | None:
    return db.scalar(select(Ticket).where(Ticket.reference == reference.strip().upper()))


def update_status(db: Session, ticket: Ticket, status: str, actor: str | None = None,
                  now: datetime | None = None) -> Ticket:
    """Change status. resolved_at is set when resolved and cleared if reopened.

    Week 7: every change is a ticket event, and the first move to "in progress" counts as
    the school's first response (it stops the response-time clock).
    """
    from app.workflow import events

    now = now or datetime.now(timezone.utc)
    old = ticket.status
    ticket.status = status
    ticket.updated_at = now
    ticket.resolved_at = now if status == "resolved" else None
    if old != status:
        events.log(db, ticket.id, "status_changed", old, status, actor, at=now)
    if status == "in_progress":
        events.mark_first_response(db, ticket, actor, now)
    if status == "resolved" and old != "resolved":
        from app.notify import messages, outbox

        outbox.notify_parent(db, ticket, *messages.parent_resolved(ticket), kind="parent_resolved")
    db.commit()
    db.refresh(ticket)
    return ticket


def _count_by(db: Session, column, keys: list[str]) -> dict[str, int]:
    """Count tickets grouped by a column; every key appears, even with 0."""
    rows = db.execute(select(column, func.count()).group_by(column)).all()
    counts = {key: 0 for key in keys}
    counts.update({value: n for value, n in rows})
    return counts


def get_stats(db: Session) -> dict:
    open_critical = db.scalar(
        select(func.count()).select_from(Ticket).where(
            Ticket.urgency == "critical", Ticket.status != "resolved"
        )
    )
    return {
        "total": db.scalar(select(func.count()).select_from(Ticket)) or 0,
        "by_status": _count_by(db, Ticket.status, STATUSES),
        "by_category": _count_by(db, Ticket.category, list(CATEGORIES)),
        "by_urgency": _count_by(db, Ticket.urgency, URGENCY_LEVELS),
        "by_language": _count_by(db, Ticket.language, list(LANGUAGES)),
        "open_critical": open_critical or 0,
    }


def ticket_timestamps(db: Session) -> list[tuple[datetime, str]]:
    """(created_at, category) for every ticket. Week 5 forecasting only needs these two fields."""
    return list(db.execute(select(Ticket.created_at, Ticket.category)).all())


# --------------------------------------------------------------------------
# Week 6: staff corrections, reply drafts, anonymisation
# --------------------------------------------------------------------------
def correct_classification(db: Session, ticket: Ticket, category: str | None, urgency: str | None,
                           actor: str, reason: str) -> tuple[Ticket, list[str]]:
    """A staff member corrects the AI's category and/or urgency (a "human override").

    The child-safety guardrails run again on the corrected values, so a person can never
    LOWER a safety ticket below what the guardrails require. (They can still resolve it.)
    Returns the ticket and the guardrails that changed the correction.
    """
    from app import audit
    from app.classifier.service import apply_guardrails

    before = {"category": ticket.category, "urgency": ticket.urgency}
    proposed = ClassificationResult(
        category=category or ticket.category,
        urgency=urgency or ticket.urgency,
        language=ticket.language,
        routed_role=ticket.routed_role,
        confidence=1.0,            # a person decided
        method="staff",
        needs_human=ticket.needs_human,
        safety_flag=ticket.safety_flag,
        reason=f"Corrected by {actor}: {reason}",
    )
    final = apply_guardrails(ticket.message, proposed)
    ticket.category, ticket.urgency = final.category, final.urgency
    ticket.routed_role, ticket.safety_flag = final.routed_role, final.safety_flag
    ticket.needs_human = final.needs_human or ticket.needs_human
    # The classification is now a person's decision (the AI's original is kept in the audit log).
    ticket.method, ticket.confidence = "staff", 1.0
    ticket.updated_at = utcnow()
    audit.record(
        db, "human_override", "staff", ticket_id=ticket.id, human_override=True, actor=actor,
        output={"before": before, "requested": {"category": proposed.category, "urgency": proposed.urgency},
                "after": {"category": final.category, "urgency": final.urgency}, "reason": reason},
        guardrails=final.guardrails_applied, commit=False,
    )
    db.commit()
    db.refresh(ticket)
    return ticket, final.guardrails_applied


def create_response(db: Session, ticket: Ticket, tone: str, draft) -> "Response":
    """Save a reply draft (status 'draft') and its audit row."""
    from app import audit
    from app.models import Response

    response = Response(
        ticket_id=ticket.id, tone=tone, language=ticket.language if draft.llm_used else "en",
        body=draft.body, original_body=draft.body, method=draft.method,
        acknowledgement_only=draft.acknowledgement_only, notes="\n".join(draft.notes),
    )
    db.add(response)
    db.flush()
    audit.record(
        db, "response_draft", draft.method, ticket_id=ticket.id, model=draft.model,
        llm_used=draft.llm_used, fallback_reason=draft.fallback_reason,
        masked_input=draft.masked_input, pii_found=draft.pii_found,
        output={"response_id": response.id, "tone": tone, "acknowledgement_only": draft.acknowledgement_only,
                "characters": len(draft.body)},
        guardrails=["acknowledgement_only"] if draft.acknowledgement_only else [], commit=False,
    )
    db.commit()
    db.refresh(response)
    return response


def list_responses(db: Session, ticket_id: int) -> list:
    from app.models import Response

    return list(db.scalars(select(Response).where(Response.ticket_id == ticket_id).order_by(Response.id)))


def get_response(db: Session, response_id: int):
    from app.models import Response

    return db.get(Response, response_id)


def edit_response(db: Session, response, body: str, actor: str):
    """Staff change the draft text. Only drafts can be edited; an AI draft edited by a person is an override."""
    from app import audit

    if response.status != "draft":
        raise ValueError("Only draft replies can be edited")
    response.body, response.edited = body, True
    audit.record(db, "response_edit", "staff", ticket_id=response.ticket_id, human_override=True,
                 actor=actor, output={"response_id": response.id, "ai_written": response.method != "template"},
                 commit=False)
    db.commit()
    db.refresh(response)
    return response


def approve_response(db: Session, response, approved_by: str):
    """A person approves the reply. Nothing reaches a parent without this step (sending is Week 7)."""
    from app import audit

    from app.workflow import events

    if response.status != "draft":
        raise ValueError("This reply is already approved")
    response.status, response.approved_by, response.approved_at = "approved", approved_by, utcnow()
    ticket = db.get(Ticket, response.ticket_id)
    if ticket is not None:
        from app.notify import messages, outbox

        events.mark_first_response(db, ticket, approved_by, response.approved_at)
        # Week 7: approving now really sends the reply (through the outbox).
        row = outbox.notify_parent(db, ticket, *messages.parent_reply(ticket, response.body),
                                   kind="parent_reply", response_id=response.id)
        response.delivery_status = row.status if row else "no_contact"
    audit.record(db, "response_approval", "staff", ticket_id=response.ticket_id, actor=approved_by,
                 human_override=response.edited,
                 output={"response_id": response.id, "edited": response.edited, "method": response.method},
                 commit=False)
    db.commit()
    db.refresh(response)
    return response


def anonymise_ticket(db: Session, ticket: Ticket, commit: bool = True) -> dict:
    """POPIA: remove the parent's name and contact, and mask personal data in the message.

    The ticket itself stays (category, dates) so statistics and forecasts still work.
    Returns the PII counts that were removed.
    """
    from app.models import Response
    from app.privacy.pii import mask_pii

    names = [ticket.parent_name] if ticket.parent_name else None
    masked = mask_pii(ticket.message, names)
    removed = dict(masked.counts)
    if ticket.parent_name:
        removed["parent_name_field"] = 1
    if ticket.parent_contact:
        removed["parent_contact_field"] = 1
    ticket.message, ticket.parent_name, ticket.parent_contact = masked.text, None, None
    for response in db.scalars(select(Response).where(Response.ticket_id == ticket.id)):
        response.body = mask_pii(response.body, names).text
        response.original_body = mask_pii(response.original_body, names).text
    # Week 7: notifications sent to the parent hold their contact details too.
    from app.models import Outbox

    for row in db.scalars(select(Outbox).where(Outbox.ticket_id == ticket.id)):
        if row.kind.startswith("parent_"):
            row.recipient = "[REMOVED]"
        row.body = mask_pii(row.body, names).text
    if commit:
        db.commit()
    return removed
