"""FastAPI application. Endpoints stay thin: the real work is in crud.py and classifier/.

Run locally:  uvicorn app.main:app --reload
Docs:         http://localhost:8000/docs
"""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager

from datetime import date

import pandas as pd
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
from app.forecasting import service as fc
from app.forecasting.data import daily_counts
from app.forecasting.forecast import MAX_HORIZON
from app.taxonomy import CATEGORIES, STAFF_ROLES, taxonomy_as_dict

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
    version="0.5.0",
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


# --------------------------------------------------------------------------
# Week 5: Predictive insights (forecasting). Staff-facing, so protected by the API key.
# --------------------------------------------------------------------------

AS_OF_HELP = "Forecast start date (YYYY-MM-DD). Defaults to today. A past date gives a backtest view."
FORECAST_CATEGORIES = list(CATEGORIES) + ["total"]


def require_jobs_token(x_jobs_token: str | None = Header(default=None)) -> None:
    """Scheduled jobs use their own token, so a leaked API key cannot trigger them."""
    expected = get_settings().jobs_token
    if not expected:
        raise HTTPException(status_code=503, detail="Scheduled jobs are disabled (JOBS_TOKEN not set)")
    if not secrets.compare_digest(x_jobs_token or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Jobs-Token header")


def _bundle(db: Session, as_of: date | None) -> dict:
    try:
        return fc.get_bundle(db, as_of)
    except fc.NotEnoughHistory as exc:
        raise HTTPException(status_code=409, detail=str(exc))


def _check_category(category: str | None) -> None:
    if category is not None and category not in FORECAST_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown category '{category}'")


def _parse_staff(staff: str | None) -> dict | None:
    """Scenario string 'admin_clerk:2,finance_clerk:1' -> {'admin_clerk': 2.0, 'finance_clerk': 1.0}."""
    if not staff:
        return None
    out = {}
    for part in staff.split(","):
        role, _, count = part.partition(":")
        role = role.strip()
        if role not in STAFF_ROLES:
            raise HTTPException(status_code=422, detail=f"Unknown staff role '{role}'")
        try:
            out[role] = max(0.0, float(count))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid staff count for '{role}'")
    return out


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-friendly rows (dates as text, floats rounded, NaN as null)."""
    df = df.copy()
    for col in ("date", "week_start"):
        if col in df:
            df[col] = df[col].dt.date.astype(str)
    df = df.astype(object).where(df.notna(), None)
    return [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()}
            for row in df.to_dict(orient="records")]


@app.get("/analytics/history", tags=["forecasting"], dependencies=[Depends(require_api_key)])
def history(start: date | None = None, end: date | None = None, category: str | None = None,
            db: Session = Depends(get_db)) -> list[dict]:
    """Actual tickets per day (for charts)."""
    _check_category(category)
    daily = daily_counts(crud.ticket_timestamps(db))
    if daily["total"].sum() == 0:
        return []
    return fc.history_rows(daily, start, end, category)


@app.get("/forecast", tags=["forecasting"], dependencies=[Depends(require_api_key)])
def forecast(days: int = Query(14, ge=1, le=MAX_HORIZON), category: str | None = None,
             as_of: date | None = Query(None, description=AS_OF_HELP),
             db: Session = Depends(get_db)) -> dict:
    """Expected tickets per day per category, with an 80% range and the method used."""
    _check_category(category)
    b = _bundle(db, as_of)
    end = b["as_of"] + pd.Timedelta(days=days - 1)
    return {
        "as_of": b["as_of"].date().isoformat(),
        "days": days,
        "is_backtest": bool(b["as_of"] < fc.today_local()),
        "chosen_models": b["evaluation"]["chosen"],
        "rows": fc.forecast_rows(b, days, category),
        "calendar_events": fc.calendar_events(b, b["as_of"] - pd.Timedelta(days=90), end),
    }


@app.get("/forecast/workload", tags=["forecasting"], dependencies=[Depends(require_api_key)])
def forecast_workload(days: int = Query(14, ge=1, le=MAX_HORIZON),
                      as_of: date | None = Query(None, description=AS_OF_HELP),
                      staff: str | None = Query(None, description="Scenario, e.g. admin_clerk:2,finance_clerk:1"),
                      db: Session = Depends(get_db)) -> dict:
    """Projected staff hours and capacity use per role, daily and weekly."""
    staff_override = _parse_staff(staff)
    b = _bundle(db, as_of)
    daily, weekly = fc.workload(b, days, staff_override)
    return {"as_of": b["as_of"].date().isoformat(), "days": days,
            "planning_buffer": round(fc.planning_buffer(b), 3),
            "daily": _records(daily), "weekly": _records(weekly)}


@app.get("/forecast/surges", tags=["forecasting"], dependencies=[Depends(require_api_key)])
def forecast_surges(days: int = Query(30, ge=1, le=MAX_HORIZON),
                    as_of: date | None = Query(None, description=AS_OF_HELP),
                    db: Session = Depends(get_db)) -> dict:
    """Days well above a normal recent day, with the likely calendar cause."""
    b = _bundle(db, as_of)
    return {"as_of": b["as_of"].date().isoformat(), "surges": fc.surges(b, days)}


@app.get("/forecast/insights", tags=["forecasting"], dependencies=[Depends(require_api_key)])
def forecast_insights(days: int = Query(14, ge=1, le=MAX_HORIZON),
                      as_of: date | None = Query(None, description=AS_OF_HELP),
                      staff: str | None = None, db: Session = Depends(get_db)) -> dict:
    """Plain-language recommendations for the principal, built only from the numbers."""
    staff_override = _parse_staff(staff)
    b = _bundle(db, as_of)
    return {"as_of": b["as_of"].date().isoformat(), "insights": fc.insights(b, days, staff_override)}


@app.get("/forecast/evaluation", tags=["forecasting"], dependencies=[Depends(require_api_key)])
def forecast_evaluation(as_of: date | None = Query(None, description=AS_OF_HELP),
                        db: Session = Depends(get_db)) -> dict:
    """Backtest accuracy per method and category, and which method was chosen."""
    return fc.evaluation_summary(_bundle(db, as_of))


@app.post("/jobs/refresh-forecast", tags=["jobs"], dependencies=[Depends(require_jobs_token)])
def refresh_forecast(days: int = Query(60, ge=1, le=MAX_HORIZON), db: Session = Depends(get_db)) -> dict:
    """Recompute and store the forecast (called by a scheduler in Week 8)."""
    fc.clear_cache()
    run = fc.save_run(db, _bundle(db, None), days)
    return {"run_id": run.id, "as_of": run.as_of, "horizon_days": run.horizon_days,
            "chosen_models": run.chosen_models}

