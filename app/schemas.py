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


class TicketStatusUpdate(BaseModel):
    status: StatusCode


class Stats(BaseModel):
    total: int
    by_status: dict[str, int]
    by_category: dict[str, int]
    by_urgency: dict[str, int]
    by_language: dict[str, int]
    open_critical: int
