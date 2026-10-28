"""Pydantic models: the shapes of data going in and out of the API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.taxonomy import CATEGORIES, GRADES, LANGUAGES, STATUSES, URGENCY_LEVELS

# Literal types are built from the taxonomy so the API rejects unknown values.
CategoryCode = Literal[tuple(CATEGORIES)]  # type: ignore[valid-type]
UrgencyCode = Literal[tuple(URGENCY_LEVELS)]  # type: ignore[valid-type]
LanguageCode = Literal[tuple(LANGUAGES)]  # type: ignore[valid-type]
StatusCode = Literal[tuple(STATUSES)]  # type: ignore[valid-type]


class ClassifyRequest(BaseModel):
    """Body for POST /classify (classify only, nothing saved)."""

    message: str = Field(min_length=1, max_length=4000)


class ClassificationResult(BaseModel):
    category: CategoryCode
    urgency: UrgencyCode
    language: LanguageCode
    routed_role: str
    confidence: float = Field(ge=0.0, le=1.0)
    method: str  # "rules", "anthropic", "gemini"
    needs_human: bool
    safety_flag: bool
    reason: str
    guardrails_applied: list[str] = []


class TicketCreate(BaseModel):
    """What a parent submits. Only `message` is required."""

    message: str = Field(min_length=1, max_length=4000)
    parent_name: str | None = Field(default=None, max_length=120)
    parent_contact: str | None = Field(default=None, max_length=120)
    learner_grade: str | None = None
    channel: str = Field(default="web", max_length=20)

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message cannot be blank")
        return v.strip()

    @field_validator("learner_grade")
    @classmethod
    def valid_grade(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        v = v.strip().upper()
        if v not in GRADES:
            raise ValueError(f"learner_grade must be one of {GRADES}")
        return v


class TicketOut(BaseModel):
    """A ticket as returned by the API (staff view)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    message: str
    parent_name: str | None
    parent_contact: str | None
    learner_grade: str | None
    channel: str
    category: str
    urgency: str
    language: str
    routed_role: str
    confidence: float
    method: str
    needs_human: bool
    safety_flag: bool
    reason: str
    status: str
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    # Week 7 workflow
    assigned_to: int | None = None
    first_response_at: datetime | None = None
    escalation_level: int = 0
    # {"status": on_track|due_soon|overdue|met, "due_at", "hours_left", "label"} (app/workflow/sla.py)
    sla: dict | None = None


class TicketCreated(BaseModel):
    """Response to a parent after submitting: no personal data echoed back."""

    id: int
    reference: str
    category: str
    category_name: str
    urgency: str
    language: str
    routed_role: str
    needs_human: bool
    safety_flag: bool
    safety_notice: str | None = None


class TicketPublic(BaseModel):
    """What anyone with a reference number may see: no message text, no personal data."""

    model_config = ConfigDict(from_attributes=True)

    reference: str
    category: str
    urgency: str
    status: str
    created_at: datetime
    updated_at: datetime
    # Week 7: has the school replied? none | sent | replied_not_emailed (approved, but no email address)
    reply_status: str = "none"


class TicketStatusUpdate(BaseModel):
    status: StatusCode


class Stats(BaseModel):
    total: int
    by_status: dict[str, int]
    by_category: dict[str, int]
    by_urgency: dict[str, int]
    by_language: dict[str, int]
    open_critical: int


# --------------------------------------------------------------------------
# Week 6: replies, staff corrections, audit log
# --------------------------------------------------------------------------
ToneCode = Literal["formal", "friendly", "urgent"]


class ResponseCreate(BaseModel):
    tone: ToneCode = "formal"


class ResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    tone: str
    language: str
    body: str
    original_body: str
    method: str
    acknowledgement_only: bool
    status: str
    edited: bool
    notes: str
    created_at: datetime
    approved_at: datetime | None
    approved_by: str | None
    # Week 7: what happened when the approved reply was sent to the parent:
    # sent | dry_run | failed | not_supported (phone number) | no_contact | None (still a draft)
    delivery_status: str | None = None


# Week 7: the staff member is now the LOGGED-IN user. The old typed-in name fields are still
# accepted (so older clients keep working) but ignored.
IGNORED_NAME = "Ignored since Week 7: the logged-in staff member is recorded"


class ResponseEdit(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    actor: str | None = Field(default=None, max_length=120, description=IGNORED_NAME)


class ResponseApprove(BaseModel):
    approved_by: str | None = Field(default=None, max_length=120, description=IGNORED_NAME)


class ClassificationCorrection(BaseModel):
    """A staff member corrects the AI. At least one of category/urgency must be given."""

    category: CategoryCode | None = None
    urgency: UrgencyCode | None = None
    actor: str | None = Field(default=None, max_length=120, description=IGNORED_NAME)
    reason: str = Field(min_length=3, max_length=300)


class CorrectionResult(BaseModel):
    ticket: TicketOut
    guardrails_applied: list[str]
    note: str | None = None


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    feature: str
    ticket_id: int | None
    method: str
    model: str | None
    llm_used: bool
    fallback_reason: str | None
    input_hash: str | None
    output: dict
    guardrails: list
    pii_found: dict
    human_override: bool
    actor: str | None


# --------------------------------------------------------------------------
# Week 7: staff login
# --------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
    active: bool


class LoginResult(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: datetime
    staff: StaffOut


# --------------------------------------------------------------------------
# Week 7: ticket events and assignment
# --------------------------------------------------------------------------
class TicketEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    type: str
    from_value: str | None
    to_value: str | None
    actor: str | None
    created_at: datetime


class AssignRequest(BaseModel):
    staff_id: int
    reason: str | None = Field(default=None, max_length=300)


class OutboxOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recipient: str
    channel: str
    kind: str
    subject: str
    ticket_id: int | None
    status: str
    error: str | None
    created_at: datetime
    sent_at: datetime | None
