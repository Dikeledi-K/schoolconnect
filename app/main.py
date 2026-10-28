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
from app import audit
from app.llm_text import llm_available, model_name
from app.privacy.pii import install_log_redaction, mask_pii
from app.privacy.retention import run_retention
from app.responses.generator import generate_draft
from app.responses.templates import load_school_info
from app.risk.fairness import fairness_report
from app.risk.report import build_pdf
from app.risk.summary import build_summary
from app.schemas import (
    AuditOut,
    ClassificationCorrection,
    CorrectionResult,
    ResponseApprove,
    ResponseCreate,
    ResponseEdit,
    ResponseOut,
)
from app.taxonomy import CATEGORIES, SENIOR_ROLES, STAFF_ROLES, taxonomy_as_dict
from app.api import auth as auth_api
from app.auth.access import can_see_ticket, visible_tickets_filter
from app.auth.deps import current_staff, require_roles
from app.models import Staff

# Week 6 (POPIA): mask personal data in every log line, from the moment the app is imported.
install_log_redaction()

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
    version="0.7.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_api.router)


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
#
# Week 7: staff endpoints need a logged-in staff member (Authorization: Bearer <token>)
# and only show tickets that person may see (app/auth/access.py). A ticket you may not
# see answers 404, not 403, so its existence is not revealed. The optional API key
# (held by the Streamlit server) still applies on top.
# --------------------------------------------------------------------------
# Forecast and risk pages: principal and deputy principal only.
SENIOR_ONLY = Depends(require_roles(*SENIOR_ROLES))


def _ticket_or_404(db: Session, ticket_id: int, staff: Staff):
    ticket = crud.get_ticket(db, ticket_id)
    if ticket is None or not can_see_ticket(staff, ticket):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket

@app.post(
    "/tickets",
    response_model=TicketCreated,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_ticket(body: TicketCreate, db: Session = Depends(get_db)) -> TicketCreated:
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
    staff: Staff = Depends(current_staff),
):
    return crud.list_tickets(
        db, status=status, category=category, urgency=urgency, language=language,
        routed_role=routed_role, needs_human=needs_human, search=search,
        limit=limit, offset=offset, visible=visible_tickets_filter(staff),
    )


@app.get("/tickets/{ticket_id}", response_model=TicketOut, dependencies=[Depends(require_api_key)])
def get_ticket(ticket_id: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    return _ticket_or_404(db, ticket_id, staff)


@app.patch(
    "/tickets/{ticket_id}/status",
    response_model=TicketOut,
    dependencies=[Depends(require_api_key)],
)
def update_ticket_status(ticket_id: int, body: TicketStatusUpdate, db: Session = Depends(get_db),
                         staff: Staff = Depends(current_staff)):
    ticket = _ticket_or_404(db, ticket_id, staff)
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


@app.get("/analytics/history", tags=["forecasting"], dependencies=[Depends(require_api_key), SENIOR_ONLY])
def history(start: date | None = None, end: date | None = None, category: str | None = None,
            db: Session = Depends(get_db)) -> list[dict]:
    """Actual tickets per day (for charts)."""
    _check_category(category)
    daily = daily_counts(crud.ticket_timestamps(db))
    if daily["total"].sum() == 0:
        return []
    return fc.history_rows(daily, start, end, category)


@app.get("/forecast", tags=["forecasting"], dependencies=[Depends(require_api_key), SENIOR_ONLY])
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


@app.get("/forecast/workload", tags=["forecasting"], dependencies=[Depends(require_api_key), SENIOR_ONLY])
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


@app.get("/forecast/surges", tags=["forecasting"], dependencies=[Depends(require_api_key), SENIOR_ONLY])
def forecast_surges(days: int = Query(30, ge=1, le=MAX_HORIZON),
                    as_of: date | None = Query(None, description=AS_OF_HELP),
                    db: Session = Depends(get_db)) -> dict:
    """Days well above a normal recent day, with the likely calendar cause."""
    b = _bundle(db, as_of)
    return {"as_of": b["as_of"].date().isoformat(), "surges": fc.surges(b, days)}


@app.get("/forecast/insights", tags=["forecasting"], dependencies=[Depends(require_api_key), SENIOR_ONLY])
def forecast_insights(days: int = Query(14, ge=1, le=MAX_HORIZON),
                      as_of: date | None = Query(None, description=AS_OF_HELP),
                      staff: str | None = None, db: Session = Depends(get_db)) -> dict:
    """Plain-language recommendations for the principal, built only from the numbers."""
    staff_override = _parse_staff(staff)
    b = _bundle(db, as_of)
    return {"as_of": b["as_of"].date().isoformat(), "insights": fc.insights(b, days, staff_override)}


@app.get("/forecast/evaluation", tags=["forecasting"], dependencies=[Depends(require_api_key), SENIOR_ONLY])
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



# --------------------------------------------------------------------------
# Week 6: replies, staff corrections, audit, risk & compliance (logged-in staff)
# --------------------------------------------------------------------------
def _response_or_404(db: Session, response_id: int, staff: Staff):
    response = crud.get_response(db, response_id)
    ticket = crud.get_ticket(db, response.ticket_id) if response else None
    if response is None or ticket is None or not can_see_ticket(staff, ticket):
        raise HTTPException(status_code=404, detail="Reply not found")
    return response


@app.post("/tickets/{ticket_id}/responses", response_model=ResponseOut, status_code=201,
          tags=["replies"], dependencies=[Depends(require_api_key)])
def draft_response(ticket_id: int, body: ResponseCreate, db: Session = Depends(get_db),
                   staff: Staff = Depends(current_staff)):
    """Draft a reply (template, or AI-rewritten and fact-checked). Staff must approve it."""
    ticket = _ticket_or_404(db, ticket_id, staff)
    return crud.create_response(db, ticket, body.tone, generate_draft(ticket, body.tone))


@app.get("/tickets/{ticket_id}/responses", response_model=list[ResponseOut], tags=["replies"],
         dependencies=[Depends(require_api_key)])
def list_responses(ticket_id: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    _ticket_or_404(db, ticket_id, staff)
    return crud.list_responses(db, ticket_id)


@app.patch("/responses/{response_id}", response_model=ResponseOut, tags=["replies"],
           dependencies=[Depends(require_api_key)])
def edit_response(response_id: int, body: ResponseEdit, db: Session = Depends(get_db),
                  staff: Staff = Depends(current_staff)):
    try:
        return crud.edit_response(db, _response_or_404(db, response_id, staff), body.body, staff.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/responses/{response_id}/approve", response_model=ResponseOut, tags=["replies"],
          dependencies=[Depends(require_api_key)])
def approve_response(response_id: int, body: ResponseApprove, db: Session = Depends(get_db),
                     staff: Staff = Depends(current_staff)):
    try:
        return crud.approve_response(db, _response_or_404(db, response_id, staff), staff.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.patch("/tickets/{ticket_id}/classification", response_model=CorrectionResult, tags=["compliance"],
           dependencies=[Depends(require_api_key)])
def correct_classification(ticket_id: int, body: ClassificationCorrection, db: Session = Depends(get_db),
                           staff: Staff = Depends(current_staff)):
    """Staff correct the AI's category/urgency. Child-safety guardrails still apply."""
    if body.category is None and body.urgency is None:
        raise HTTPException(status_code=422, detail="Give a category, an urgency, or both")
    ticket = _ticket_or_404(db, ticket_id, staff)
    ticket, applied = crud.correct_classification(db, ticket, body.category, body.urgency, staff.name, body.reason)
    note = None
    if applied:
        note = ("The child-safety guardrails kept this ticket at a safe level. "
                "A person must still handle it; you can resolve it when it is dealt with.")
    return CorrectionResult(ticket=TicketOut.model_validate(ticket), guardrails_applied=applied, note=note)


@app.get("/tickets/{ticket_id}/audit", response_model=list[AuditOut], tags=["compliance"],
         dependencies=[Depends(require_api_key)])
def ticket_audit(ticket_id: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    """Every AI decision and human override for one ticket (transparency)."""
    _ticket_or_404(db, ticket_id, staff)
    return audit.for_ticket(db, ticket_id)


@app.post("/privacy/tickets/{ticket_id}/anonymise", tags=["compliance"], dependencies=[Depends(require_api_key)])
def anonymise_ticket(ticket_id: int,
                     actor: str | None = Query(None, max_length=120, description="Ignored since Week 7"),
                     db: Session = Depends(get_db), staff: Staff = Depends(current_staff)) -> dict:
    """POPIA: remove a parent's personal data from a ticket on request (keeps the statistics)."""
    ticket = _ticket_or_404(db, ticket_id, staff)
    removed = crud.anonymise_ticket(db, ticket, commit=False)
    audit.record(db, "anonymise", "staff", ticket_id=ticket_id, actor=staff.name, human_override=True,
                 pii_found=removed, output={"reason": "data subject request"})
    return {"ticket_id": ticket_id, "removed": removed}


@app.get("/risk/summary", tags=["compliance"], dependencies=[Depends(require_api_key), SENIOR_ONLY])
def risk_summary(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)) -> dict:
    """AI decisions, guardrails, PII masked, overrides, fairness and injection results (counts only)."""
    return build_summary(db, days)


@app.get("/risk/fairness", tags=["compliance"], dependencies=[Depends(require_api_key), SENIOR_ONLY])
def risk_fairness(db: Session = Depends(get_db)) -> dict:
    return fairness_report(db)


@app.get("/risk/report.pdf", tags=["compliance"], dependencies=[Depends(require_api_key), SENIOR_ONLY])
def risk_report(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    """Download the risk evaluation report as a PDF."""
    from fastapi.responses import Response as HTTPResponse

    pdf = build_pdf(build_summary(db, days), load_school_info()["school"]["name"])
    return HTTPResponse(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="schoolconnect-risk-report.pdf"'})


@app.post("/jobs/retention", tags=["jobs"], dependencies=[Depends(require_jobs_token)])
def retention_job(dry_run: bool = True, db: Session = Depends(get_db)) -> dict:
    """POPIA retention: anonymise resolved tickets older than RETENTION_DAYS. Dry run by default."""
    return run_retention(db, dry_run=dry_run)
