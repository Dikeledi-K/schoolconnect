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
) -> list[Ticket]:
    """Newest first. Every filter is optional."""
    query = select(Ticket)
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


def update_status(db: Session, ticket: Ticket, status: str) -> Ticket:
    """Change status. resolved_at is set when resolved and cleared if reopened."""
    ticket.status = status
    now = datetime.now(timezone.utc)
    ticket.updated_at = now
    ticket.resolved_at = now if status == "resolved" else None
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
