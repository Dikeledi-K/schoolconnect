"""Weeks 3-4 endpoints: analytics dashboard data and weekly business reports.

Access (POPIA least privilege): the principal sees every department, the deputy principal sees
the whole school and learner welfare, everyone else sees their own department.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response as HTTPResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.analytics.insights import build_insights, template_summary
from app.analytics.metrics import compute_metrics, last_full_week, today_local, weekly_trends
from app.auth.deps import current_staff
from app.db import get_db
from app.models import Staff, WeeklyReport
from app.reports import weekly
from app.taxonomy import DEPARTMENT_NAMES

router = APIRouter(tags=["analytics & reports"])


def _scope(staff: Staff, scope: str | None) -> str:
    """The department to show: the one asked for (if allowed), else this person's default."""
    if scope is None:
        if not weekly.allowed_scopes(staff):
            raise HTTPException(status_code=403, detail="Your role has no department reports")
        return weekly.default_scope(staff)
    if scope not in DEPARTMENT_NAMES:
        raise HTTPException(status_code=422, detail=f"Unknown department '{scope}'")
    if scope not in weekly.allowed_scopes(staff):
        raise HTTPException(status_code=403, detail="You may not see that department's figures")
    return scope


@router.get("/analytics/scopes")
def analytics_scopes(staff: Staff = Depends(current_staff)) -> list[dict]:
    """Departments this person may see, default first."""
    return [{"key": k, "name": DEPARTMENT_NAMES[k]} for k in weekly.allowed_scopes(staff)]


@router.get("/analytics/summary")
def analytics_summary(start: date | None = None, end: date | None = None, scope: str | None = None,
                      db: Session = Depends(get_db), staff: Staff = Depends(current_staff)) -> dict:
    """Figures for a period (default: last completed week) compared with the period before,
    plus plain-language insights and a summary."""
    scope = _scope(staff, scope)
    if start is None or end is None:
        default_start, default_end = last_full_week()
        start, end = start or default_start, end or default_end
    try:
        metrics = compute_metrics(db, start, end, scope)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    insights = build_insights(metrics)
    return {"metrics": metrics, "insights": insights, "summary": template_summary(metrics, insights)}


@router.get("/analytics/trends")
def analytics_trends(weeks: int = Query(12, ge=1, le=52), scope: str | None = None,
                     db: Session = Depends(get_db), staff: Staff = Depends(current_staff)) -> dict:
    """Week-by-week messages, median first response and on-time rate for the last `weeks` weeks."""
    scope = _scope(staff, scope)
    return {"scope": scope, "scope_name": DEPARTMENT_NAMES[scope], "weeks": weekly_trends(db, scope, weeks)}


# --------------------------------------------------------------------------
# Weekly reports
# --------------------------------------------------------------------------
class ReportRequest(BaseModel):
    week_start: date | None = None     # a Monday; default: last completed week
    scope: str | None = None


def _report_out(report: WeeklyReport) -> dict:
    d = report.data
    return {"id": report.id, "week_start": report.week_start, "week_end": d["week_end"],
            "scope": report.scope, "scope_name": DEPARTMENT_NAMES.get(report.scope, report.scope),
            "created_at": report.created_at.isoformat(timespec="minutes"), "created_by": report.created_by,
            "summary": d["summary"], "summary_method": report.summary_method,
            "messages": d["metrics"]["volume"]["total"],
            "wins": sum(i["type"] == "win" for i in d["insights"]),
            "concerns": sum(i["type"] == "concern" for i in d["insights"])}


@router.get("/reports/weeks")
def report_weeks(count: int = Query(12, ge=1, le=52), staff: Staff = Depends(current_staff)) -> list[str]:
    """Mondays of the most recent completed weeks (for the "choose a week" list)."""
    last_monday = last_full_week()[0]
    return [(last_monday - timedelta(weeks=i)).isoformat() for i in range(count)]


@router.get("/reports")
def list_reports(scope: str | None = None, db: Session = Depends(get_db),
                 staff: Staff = Depends(current_staff)) -> list[dict]:
    scopes = [_scope(staff, scope)] if scope else weekly.allowed_scopes(staff)
    return [_report_out(r) for r in weekly.list_reports(db, scopes)]


@router.post("/reports/weekly", status_code=201)
def create_report(body: ReportRequest, db: Session = Depends(get_db),
                  staff: Staff = Depends(current_staff)) -> dict:
    """Make (or remake) the weekly report for one department and week."""
    scope = _scope(staff, body.scope)
    week_start = body.week_start or last_full_week()[0]
    try:
        report = weekly.generate_report(db, week_start, scope, staff.name)
    except weekly.ReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _report_out(report)


@router.get("/reports/{report_id}/pdf")
def report_pdf(report_id: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    report = db.get(WeeklyReport, report_id)
    if report is None or report.scope not in weekly.allowed_scopes(staff):
        raise HTTPException(status_code=404, detail="Report not found")
    name = f"schoolconnect-weekly-{report.scope}-{report.week_start}.pdf"
    return HTTPResponse(content=report.pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})
