"""Week 6: write and read the AI audit log.

Every AI decision (classification, reply draft) and every human override gets one row,
so the school can answer "what did the AI decide, why, and did a person change it?".
Rows never contain raw personal data: only a hash of the MASKED input and PII counts.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIAuditLog


def hash_text(text: str) -> str:
    """SHA-256 of the (already masked) input. Lets us prove what was sent without storing it."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record(
    db: Session,
    feature: str,
    method: str,
    *,
    ticket_id: int | None = None,
    model: str | None = None,
    llm_used: bool = False,
    fallback_reason: str | None = None,
    masked_input: str | None = None,
    output: dict | None = None,
    guardrails: list[str] | None = None,
    pii_found: dict | None = None,
    human_override: bool = False,
    actor: str | None = None,
    commit: bool = True,
) -> AIAuditLog:
    entry = AIAuditLog(
        feature=feature,
        method=method,
        ticket_id=ticket_id,
        model=model,
        llm_used=llm_used,
        fallback_reason=fallback_reason,
        input_hash=hash_text(masked_input) if masked_input is not None else None,
        output=output or {},
        guardrails=guardrails or [],
        pii_found=pii_found or {},
        human_override=human_override,
        actor=actor,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry


def for_ticket(db: Session, ticket_id: int) -> list[AIAuditLog]:
    query = select(AIAuditLog).where(AIAuditLog.ticket_id == ticket_id).order_by(AIAuditLog.id)
    return list(db.scalars(query))


def since(db: Session, start: datetime) -> list[AIAuditLog]:
    query = select(AIAuditLog).where(AIAuditLog.created_at >= start).order_by(AIAuditLog.id)
    return list(db.scalars(query))
