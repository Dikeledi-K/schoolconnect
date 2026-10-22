"""SQLAlchemy ORM models (database tables)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    """All timestamps are stored in UTC."""
    return datetime.now(timezone.utc)


class Ticket(Base):
    """One parent message and everything we decided about it."""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Human-friendly reference given to the parent, e.g. SC-20260122-0007.
    reference: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # What the parent sent. Name/contact are optional and are NEVER sent to an LLM.
    message: Mapped[str] = mapped_column(Text)
    parent_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parent_contact: Mapped[str | None] = mapped_column(String(120), nullable=True)
    learner_grade: Mapped[str | None] = mapped_column(String(4), nullable=True)
    channel: Mapped[str] = mapped_column(String(20), default="web")

    # Classification results.
    category: Mapped[str] = mapped_column(String(30), index=True)
    urgency: Mapped[str] = mapped_column(String(10), index=True)
    language: Mapped[str] = mapped_column(String(10), index=True)
    routed_role: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(30))  # "rules", "anthropic", "gemini"
    needs_human: Mapped[bool] = mapped_column(Boolean, default=False)
    safety_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text, default="")

    # Workflow.
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
