"""Week 4: build, store and list weekly business reports.

A report covers one COMPLETED week (Monday to Sunday) for the whole school or one department:
figures compared with the previous week, an 8-week trend, plain-language wins and concerns,
an executive summary, and next week's outlook from the Week 5 forecast.

Who may see which report (POPIA least privilege, same idea as Week 7 ticket access):
- Principal: every report.
- Deputy principal: the whole-school report and the learner-welfare report.
- Everyone else: their own department's report only.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analytics.insights import build_insights, executive_summary, outlook
from app.analytics.metrics import compute_metrics, last_full_week, today_local, weekly_trends
from app.config import Settings
from app.models import Staff, WeeklyReport
from app.reports.pdf import build_pdf
from app.responses.templates import load_school_info
from app.taxonomy import DEPARTMENT_NAMES, PRINCIPAL_ROLE, SCHOOL_SCOPE, STAFF_ROLES

TREND_WEEKS = 8


class ReportError(ValueError):
    """The report cannot be made (e.g. the week has not finished yet)."""


# --------------------------------------------------------------------------
# Access
# --------------------------------------------------------------------------
def allowed_scopes(staff: Staff) -> list[str]:
    if staff.role == PRINCIPAL_ROLE:
        return list(DEPARTMENT_NAMES)
    if staff.role == "deputy_principal":
        return [SCHOOL_SCOPE, "deputy_principal"]
    return [staff.role] if staff.role in STAFF_ROLES else []


def default_scope(staff: Staff) -> str:
    return allowed_scopes(staff)[0]


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------
def check_week(week_start: date, today: date | None = None) -> date:
    """A report week must start on a Monday and be over already. Returns the Sunday."""
    if week_start.weekday() != 0:
        raise ReportError("A report week starts on a Monday")
    week_end = week_start + timedelta(days=6)
    if week_end >= (today or today_local()):
        raise ReportError("That week has not finished yet; reports cover completed weeks only")
    return week_end


def build_report_data(db: Session, week_start: date, scope: str, include_outlook: bool = True,
                      settings: Settings | None = None, now: datetime | None = None) -> dict:
    if scope not in DEPARTMENT_NAMES:
        raise ReportError(f"Unknown department '{scope}'")
    now = now or datetime.now(timezone.utc)
    week_end = check_week(week_start, today_local(now))
    metrics = compute_metrics(db, week_start, week_end, scope, now=now)
    insights = build_insights(metrics)
    summary, method = executive_summary(db, metrics, insights, settings)
    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "scope": scope,
        "scope_name": DEPARTMENT_NAMES[scope],
        "generated_at": now.isoformat(timespec="minutes"),
        "summary": summary,
        "summary_method": method,
        "insights": insights,
        "metrics": metrics,
        "trends": weekly_trends(db, scope, TREND_WEEKS, end=week_end, now=now),
        "outlook": outlook(db, scope, week_end + timedelta(days=1)) if include_outlook else None,
    }


def generate_report(db: Session, week_start: date, scope: str, created_by: str,
                    include_outlook: bool = True, settings: Settings | None = None,
                    now: datetime | None = None) -> WeeklyReport:
    """Build the report and its PDF, and store it. A report for the same week and department
    is replaced (the latest version wins)."""
    data = build_report_data(db, week_start, scope, include_outlook, settings, now)
    pdf = build_pdf(data, load_school_info()["school"]["name"])
    db.execute(delete(WeeklyReport).where(WeeklyReport.week_start == data["week_start"],
                                          WeeklyReport.scope == scope))
    report = WeeklyReport(week_start=data["week_start"], scope=scope, created_by=created_by,
                          summary_method=data["summary_method"], data=data, pdf=pdf)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def find_report(db: Session, week_start: date, scope: str) -> WeeklyReport | None:
    return db.scalar(select(WeeklyReport).where(WeeklyReport.week_start == week_start.isoformat(),
                                                WeeklyReport.scope == scope))


def list_reports(db: Session, scopes: list[str], limit: int = 100) -> list[WeeklyReport]:
    if not scopes:
        return []
    query = (select(WeeklyReport).where(WeeklyReport.scope.in_(scopes))
             .order_by(WeeklyReport.week_start.desc(), WeeklyReport.scope).limit(limit))
    return list(db.scalars(query))


def run_weekly_job(db: Session, week_start: date | None = None, force: bool = False,
                   include_outlook: bool = True, now: datetime | None = None) -> dict:
    """Scheduled job: make last week's report for the whole school and every department, then
    tell the people who may read each one. Reports that already exist are kept unless force."""
    from app.notify import outbox
    from app.workflow.assignment import active_staff

    now = now or datetime.now(timezone.utc)
    week_start = week_start or last_full_week(today_local(now))[0]
    created, skipped = [], []
    for scope in DEPARTMENT_NAMES:
        if find_report(db, week_start, scope) and not force:
            skipped.append(scope)
            continue
        generate_report(db, week_start, scope, "scheduler", include_outlook=include_outlook, now=now)
        created.append(scope)
        # Who to tell: principal(s) for the whole school; the department's staff (and the
        # principal) for a department. Email says only that a report is ready: no figures.
        roles = [PRINCIPAL_ROLE] if scope == SCHOOL_SCOPE else [scope]
        for role in roles:
            for staff in active_staff(db, role):
                outbox.notify_staff(
                    db, staff,
                    f"SchoolConnect: weekly report ready ({DEPARTMENT_NAMES[scope]})",
                    f"Hello {staff.name},\n\nThe weekly report for {DEPARTMENT_NAMES[scope]}, week of "
                    f"{week_start.day} {week_start:%B %Y}, is ready.\n\nOpen SchoolConnect > Weekly reports "
                    "to read or download it.\n\nSchoolConnect",
                    kind="staff_weekly_report")
    db.commit()
    return {"week_start": week_start.isoformat(), "created": created, "skipped_existing": skipped}
