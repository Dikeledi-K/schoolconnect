"""Week 4: weekly business reports (building, storing, access by role, scheduled job, PDF)."""

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.analytics.metrics import last_full_week
from app.models import Outbox, WeeklyReport
from app.reports import weekly
from app.taxonomy import DEPARTMENT_NAMES
from tests.conftest import add_staff
from tests.test_analytics import add, at

NOW = datetime(2026, 3, 9, 14, 0, tzinfo=ZoneInfo("Africa/Johannesburg"))
MONDAY = date(2026, 3, 2)


@pytest.fixture
def week_data(db_session):
    add(db_session, at(2, 9), first=at(2, 10), contact="parent@example.com")
    add(db_session, at(3, 9), category="fees_exemptions", urgency="medium", first=at(6, 9))
    add(db_session, at(4, 9), category="learner_welfare", urgency="high", first=at(4, 9, 30), safety=True)
    add(db_session, at(24, 9, month=2), first=at(24, 11, month=2))
    return db_session


# ---------------------------------------------------------------- building and storing
def test_report_is_built_stored_and_replaced(week_data):
    db = week_data
    r = weekly.generate_report(db, MONDAY, "school", "Ms Dlamini", include_outlook=False, now=NOW)
    assert r.pdf.startswith(b"%PDF") and len(r.pdf) > 3000
    assert r.data["week_end"] == "2026-03-08" and r.data["metrics"]["volume"]["total"] == 3
    assert r.data["summary"] and len(r.data["trends"]) == weekly.TREND_WEEKS
    assert any(i["type"] == "concern" for i in r.data["insights"])     # the fees reply was late
    dump = json.dumps(r.data)
    assert "example.com" not in dump and "SECRET MESSAGE" not in dump

    weekly.generate_report(db, MONDAY, "school", "Mr Nel", include_outlook=False, now=NOW)
    stored = db.query(WeeklyReport).filter_by(week_start="2026-03-02", scope="school").all()
    assert len(stored) == 1 and stored[0].created_by == "Mr Nel"     # the latest version wins


def test_department_report_only_has_its_topics(week_data):
    r = weekly.generate_report(week_data, MONDAY, "finance_clerk", "x", include_outlook=False, now=NOW)
    assert list(r.data["metrics"]["volume"]["by_category"]) == ["fees_exemptions"]
    assert r.data["scope_name"] == "Finance office"


def test_only_completed_weeks_starting_on_monday(db_session):
    with pytest.raises(weekly.ReportError, match="Monday"):
        weekly.check_week(date(2026, 3, 3), today=date(2026, 3, 20))
    with pytest.raises(weekly.ReportError, match="not finished"):
        weekly.check_week(date(2026, 3, 9), today=date(2026, 3, 15))     # Sunday: week not over yet
    assert weekly.check_week(date(2026, 3, 9), today=date(2026, 3, 16)) == date(2026, 3, 15)


def test_allowed_scopes_by_role(db_session):
    def scopes(role):
        return weekly.allowed_scopes(add_staff(db_session, f"Test {role}", role))
    assert scopes("principal") == list(DEPARTMENT_NAMES)
    assert scopes("deputy_principal") == ["school", "deputy_principal"]
    assert scopes("finance_clerk") == ["finance_clerk"]


# ---------------------------------------------------------------- scheduled job
def test_weekly_job_makes_every_report_once_and_tells_readers(week_data):
    db = week_data
    add_staff(db, "Mrs Pillay", "finance_clerk")
    add_staff(db, "Ms Dlamini", "principal")
    first = weekly.run_weekly_job(db, week_start=MONDAY, include_outlook=False, now=NOW)
    assert first["created"] == list(DEPARTMENT_NAMES) and first["skipped_existing"] == []
    again = weekly.run_weekly_job(db, week_start=MONDAY, include_outlook=False, now=NOW)
    assert again["created"] == [] and len(again["skipped_existing"]) == len(DEPARTMENT_NAMES)
    forced = weekly.run_weekly_job(db, week_start=MONDAY, force=True, include_outlook=False, now=NOW)
    assert forced["created"] == list(DEPARTMENT_NAMES)

    mails = db.query(Outbox).filter(Outbox.kind == "staff_weekly_report").all()
    to = {m.recipient for m in mails}
    assert any(r.startswith("principal.") for r in to) and any(r.startswith("finance_clerk.") for r in to)
    for m in mails:   # "your report is ready" only: no figures, no personal data
        assert "Weekly reports" in m.body and "messages" not in m.body and "example.com" not in m.body


# ---------------------------------------------------------------- API
def test_api_access_by_role(client, login_as, week_data):
    _, teacher = login_as("class_teacher", "Mr Nel")
    _, deputy = login_as("deputy_principal", "Mr Mokoena")
    assert [s["key"] for s in client.get("/analytics/scopes").json()] == list(DEPARTMENT_NAMES)
    assert [s["key"] for s in client.get("/analytics/scopes", headers=deputy).json()] == ["school", "deputy_principal"]
    params = {"start": "2026-03-02", "end": "2026-03-08"}
    assert client.get("/analytics/summary", params={**params, "scope": "school"}, headers=teacher).status_code == 403
    assert client.get("/analytics/summary", params={**params, "scope": "janitor"}).status_code == 422
    mine = client.get("/analytics/summary", params=params, headers=teacher).json()     # default: own department
    assert mine["metrics"]["scope"]["key"] == "class_teacher" and mine["insights"]
    assert client.get("/analytics/summary", params={"start": "2026-03-08", "end": "2026-03-02"}).status_code == 422
    assert client.get("/analytics/trends", params={"weeks": 4}, headers=teacher).json()["scope"] == "class_teacher"


def test_api_reports_and_pdf_access(client, login_as, week_data):
    _, teacher = login_as("class_teacher", "Mr Nel")
    week = last_full_week()[0].isoformat()
    made = client.post("/reports/weekly", json={"week_start": week, "scope": "school"})
    assert made.status_code == 201 and made.json()["scope_name"] == DEPARTMENT_NAMES["school"]
    assert client.post("/reports/weekly", json={"week_start": week, "scope": "school"}, headers=teacher).status_code == 403
    assert client.post("/reports/weekly", json={"week_start": "2026-03-03", "scope": "school"}).status_code == 422
    ours = client.post("/reports/weekly", json={"week_start": week}, headers=teacher).json()   # own department
    assert ours["scope"] == "class_teacher"

    assert {r["scope"] for r in client.get("/reports").json()} == {"school", "class_teacher"}
    assert [r["scope"] for r in client.get("/reports", headers=teacher).json()] == ["class_teacher"]
    pdf = client.get(f"/reports/{made.json()['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get(f"/reports/{made.json()['id']}/pdf", headers=teacher).status_code == 404
    assert len(client.get("/reports/weeks", params={"count": 3}).json()) == 3


def test_weekly_reports_job_endpoint(client, set_env):
    assert client.post("/jobs/weekly-reports").status_code == 503          # jobs disabled without a token
    set_env(JOBS_TOKEN="tok")
    assert client.post("/jobs/weekly-reports", headers={"X-Jobs-Token": "wrong"}).status_code == 401
    ok = client.post("/jobs/weekly-reports", headers={"X-Jobs-Token": "tok"})
    assert ok.status_code == 200 and ok.json()["created"] == list(DEPARTMENT_NAMES)
    again = client.post("/jobs/weekly-reports", headers={"X-Jobs-Token": "tok"}).json()
    assert again["created"] == []
    bad = client.post("/jobs/weekly-reports", params={"week_start": "2026-03-03"}, headers={"X-Jobs-Token": "tok"})
    assert bad.status_code == 422


def test_reports_need_a_login(anon_client):
    assert anon_client.get("/reports").status_code == 401
    assert anon_client.get("/analytics/summary").status_code == 401
