"""SQLAlchemy ORM models (database tables)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
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


class ForecastRun(Base):
    """Week 5: one stored forecast, so results are reproducible and comparable over time."""

    __tablename__ = "forecast_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    as_of: Mapped[str] = mapped_column(String(10))       # forecast start date, YYYY-MM-DD
    horizon_days: Mapped[int] = mapped_column(Integer)
    chosen_models: Mapped[dict] = mapped_column(JSON)     # {category: method}
    metrics: Mapped[dict] = mapped_column(JSON)           # backtest results
    forecast: Mapped[list] = mapped_column(JSON)          # forecast rows


class Response(Base):
    """Week 6: a reply to a parent. Drafted by template or AI, always approved by staff."""

    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(Integer, index=True)
    tone: Mapped[str] = mapped_column(String(10))            # formal | friendly | urgent
    language: Mapped[str] = mapped_column(String(10))
    body: Mapped[str] = mapped_column(Text)                  # current text (after any staff edits)
    original_body: Mapped[str] = mapped_column(Text)         # the draft exactly as generated
    method: Mapped[str] = mapped_column(String(30))          # "template", "anthropic", "gemini"
    acknowledgement_only: Mapped[bool] = mapped_column(Boolean, default=False)  # welfare/safety
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | approved
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")     # messages for staff, e.g. "translate"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)


class AIAuditLog(Base):
    """Week 6: one row per AI decision or human override, for transparency and POPIA accountability.

    Never stores raw personal data: the input is kept only as a SHA-256 hash of the MASKED text.
    """

    __tablename__ = "ai_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    feature: Mapped[str] = mapped_column(String(30), index=True)  # classification | response_draft | human_override | retention
    ticket_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    method: Mapped[str] = mapped_column(String(30))               # rules | template | anthropic | gemini | staff
    model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    llm_used: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    guardrails: Mapped[list] = mapped_column(JSON, default=list)
    pii_found: Mapped[dict] = mapped_column(JSON, default=dict)   # counts per PII type, never the values
    human_override: Mapped[bool] = mapped_column(Boolean, default=False)
    actor: Mapped[str | None] = mapped_column(String(120), nullable=True)  # staff member for overrides


class Staff(Base):
    """Week 7: a staff account. Roles come from taxonomy.ACCOUNT_ROLES."""

    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)   # stored lower-case
    role: Mapped[str] = mapped_column(String(30), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_hash: Mapped[str] = mapped_column(String(200))   # "pbkdf2_sha256$iterations$salt$hash"
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StaffSession(Base):
    """Week 7: a login. Only the SHA-256 hash of the token is stored, so a database leak
    does not give anyone a working token."""

    __tablename__ = "staff_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    staff_id: Mapped[int] = mapped_column(Integer, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
