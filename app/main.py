"""FastAPI application. Endpoints stay thin: the real work is in crud.py and classifier/.

Run locally:  uvicorn app.main:app --reload
Docs:         http://localhost:8000/docs
"""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import crud
from app.classifier import classify_message
from app.config import get_settings
from app.db import get_db, init_db
from app.schemas import (
    CategoryCode,
    ClassificationResult,
    ClassifyRequest,
    LanguageCode,
    Stats,
    StatusCode,
    TicketCreate,
    TicketCreated,
    TicketOut,
    TicketPublic,
    TicketStatusUpdate,
    UrgencyCode,
)
from app.taxonomy import CATEGORIES, taxonomy_as_dict

SAFETY_NOTICE = (
    "If a child is in immediate danger call 10111 (SAPS) or 112 from a cellphone. "
    "A staff member has been alerted and will contact you."
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # create tables on startup
    yield


app = FastAPI(
    title="SchoolConnect API",
    description="AI help desk for South African public schools.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Protects endpoints that write data or return personal data.

    If API_KEY is empty (local development), everything is open.
    compare_digest avoids leaking the key through timing differences.
    """
    expected = get_settings().api_key
    if expected and not secrets.compare_digest(x_api_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")


# --------------------------------------------------------------------------
# Public endpoints
# --------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "llm_provider": settings.llm_provider}


@app.get("/taxonomy")
def taxonomy() -> dict:
    return taxonomy_as_dict()


@app.post("/classify", response_model=ClassificationResult)
def classify(body: ClassifyRequest) -> ClassificationResult:
    """Classify a message without saving anything (useful for demos and testing)."""
    return classify_message(body.message)


@app.get("/stats", response_model=Stats)
def stats(db: Session = Depends(get_db)):
    """Counts only, no personal data, so it is public."""
    return crud.get_stats(db)


@app.get("/tickets/by-reference/{reference}", response_model=TicketPublic)
def ticket_by_reference(reference: str, db: Session = Depends(get_db)):
    """Parents check progress with their reference. Returns no personal data."""
    ticket = crud.get_ticket_by_reference(db, reference)
    if ticket is None:
        raise HTTPException(status_code=404, detail="No ticket with that reference")
    return ticket


# --------------------------------------------------------------------------
# Protected endpoints (write data or expose personal data)
# --------------------------------------------------------------------------
@app.post(
    "/tickets",
    response_model=TicketCreated,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_ticket(body: TicketCreate, db: Session = Depends(get_db)) -> TicketCreated:
    # Only the message text goes to the classifier, never name/contact.
    result = classify_message(body.message)
    ticket = crud.create_ticket(db, body, result)
    return TicketCreated(
        id=ticket.id,
        reference=ticket.reference,
        category=ticket.category,
        category_name=CATEGORIES[ticket.category].display_name,
        urgency=ticket.urgency,
        language=ticket.language,
        routed_role=ticket.routed_role,
        needs_human=ticket.needs_human,
        safety_flag=ticket.safety_flag,
        safety_notice=SAFETY_NOTICE if ticket.urgency == "critical" else None,
    )


@app.get("/tickets", response_model=list[TicketOut], dependencies=[Depends(require_api_key)])
def list_tickets(
    status: StatusCode | None = None,
    category: CategoryCode | None = None,
    urgency: UrgencyCode | None = None,
    language: LanguageCode | None = None,
    routed_role: str | None = None,
    needs_human: bool | None = None,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return crud.list_tickets(
        db, status=status, category=category, urgency=urgency, language=language,
        routed_role=routed_role, needs_human=needs_human, search=search,
        limit=limit, offset=offset,
    )


@app.get("/tickets/{ticket_id}", response_model=TicketOut, dependencies=[Depends(require_api_key)])
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    ticket = crud.get_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@app.patch(
    "/tickets/{ticket_id}/status",
    response_model=TicketOut,
    dependencies=[Depends(require_api_key)],
)
def update_ticket_status(ticket_id: int, body: TicketStatusUpdate, db: Session = Depends(get_db)):
    ticket = crud.get_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return crud.update_status(db, ticket, body.status)
