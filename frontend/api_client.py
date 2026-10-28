"""Tiny HTTP client for the SchoolConnect API. The ONLY way the frontend talks to the backend.

Configuration (first match wins):
1. Streamlit secrets (.streamlit/secrets.toml or Streamlit Cloud settings): API_BASE_URL, API_KEY
2. Environment variables with the same names
3. Default: http://localhost:8000, no key

Week 7: after a staff login the bearer token lives in st.session_state["token"] (per browser
session, never on disk) and is sent with every request as  Authorization: Bearer <token>.
"""

from __future__ import annotations

import os

import requests
import streamlit as st

TIMEOUT_SECONDS = 60  # the first (uncached) forecast takes a few seconds
TOKEN_KEY = "token"


class ApiError(Exception):
    """A friendly error message the pages can show to the user (never a stack trace)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _setting(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001 - no secrets file is fine
        pass
    return os.getenv(name, default)


def base_url() -> str:
    return _setting("API_BASE_URL", "http://localhost:8000").rstrip("/")


# ---- Login token (kept in this browser session only) ------------------------
def current_token() -> str | None:
    try:
        return st.session_state.get(TOKEN_KEY)
    except Exception:  # noqa: BLE001 - outside a Streamlit session (e.g. tests)
        return None


def clear_token() -> None:
    try:
        for key in (TOKEN_KEY, "staff"):
            st.session_state.pop(key, None)
    except Exception:  # noqa: BLE001
        pass


def _headers() -> dict:
    headers = {}
    key = _setting("API_KEY")
    if key:
        headers["X-API-Key"] = key
    token = current_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _detail(response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return ""
    return detail if isinstance(detail, str) else ""


def _raise_for(response) -> None:
    """Turn an error response into a message a parent or staff member understands."""
    code = response.status_code
    if code == 401:
        if current_token():
            clear_token()
            raise ApiError("Your login has expired. Please log in again.", code)
        raise ApiError(_detail(response) or "Please log in.", code)
    if code == 403:
        raise ApiError(_detail(response) or "You do not have access to this.", code)
    if code == 404:
        raise ApiError("Not found.", code)
    if code in (409, 423):
        # e.g. "no ticket history yet", "already approved", "account locked"
        raise ApiError(_detail(response) or "That cannot be done right now.", code)
    if code == 422:
        raise ApiError(_detail(response) or "Some of the information entered is not valid. "
                       "Please check and try again.", code)
    if code >= 400:
        raise ApiError(f"Something went wrong on the server ({code}). Please try again.", code)


def _request(method: str, path: str, **kwargs):
    try:
        response = requests.request(
            method, base_url() + path, headers=_headers(), timeout=TIMEOUT_SECONDS, **kwargs
        )
    except requests.RequestException as exc:
        raise ApiError(
            f"Could not reach the SchoolConnect API at {base_url()}. Is it running?"
        ) from exc
    _raise_for(response)
    return response.json() if response.content else None


# ---- Endpoints -----------------------------------------------------------
def health() -> dict:
    return _request("GET", "/health")


@st.cache_data(ttl=300)
def taxonomy() -> dict:
    """Cached for 5 minutes: the taxonomy rarely changes (and is public)."""
    return _request("GET", "/taxonomy")


def classify(message: str) -> dict:
    return _request("POST", "/classify", json={"message": message})


def create_ticket(message: str, parent_name: str | None, parent_contact: str | None,
                  learner_grade: str | None) -> dict:
    body = {
        "message": message,
        "parent_name": parent_name or None,
        "parent_contact": parent_contact or None,
        "learner_grade": learner_grade or None,
        "channel": "web",
    }
    return _request("POST", "/tickets", json=body)


def list_tickets(**filters) -> list[dict]:
    params = {k: v for k, v in filters.items() if v not in (None, "", "All")}
    return _request("GET", "/tickets", params=params)


def ticket_by_reference(reference: str) -> dict:
    return _request("GET", f"/tickets/by-reference/{reference.strip()}")


def update_status(ticket_id: int, status: str) -> dict:
    return _request("PATCH", f"/tickets/{ticket_id}/status", json={"status": status})


def stats() -> dict:
    return _request("GET", "/stats")


# ---- Week 7: login, my work, assignment, timeline -------------------------
def login(email: str, password: str) -> dict:
    return _request("POST", "/auth/login", json={"email": email, "password": password})


def logout() -> None:
    try:
        _request("POST", "/auth/logout")
    except ApiError:
        pass          # already expired: nothing to do
    clear_token()


def me() -> dict:
    return _request("GET", "/auth/me")


def my_work() -> list[dict]:
    return _request("GET", "/workflow/my-work")


def staff_list() -> list[dict]:
    return _request("GET", "/staff")


def assign(ticket_id: int, staff_id: int, reason: str | None = None) -> dict:
    return _request("POST", f"/tickets/{ticket_id}/assign", json={"staff_id": staff_id, "reason": reason})


def ticket_events(ticket_id: int) -> list[dict]:
    return _request("GET", f"/tickets/{ticket_id}/events")


def ticket_outbox(ticket_id: int) -> list[dict]:
    return _request("GET", f"/tickets/{ticket_id}/outbox")


# ---- Week 7: fee exemptions ------------------------------------------------
def fee_exemptions(status: str | None = None) -> list[dict]:
    return _request("GET", "/fee-exemptions", params={"status": status} if status else None)


def start_fee_exemption(ticket_id: int) -> dict:
    return _request("POST", f"/tickets/{ticket_id}/fee-exemption")


def fee_step(exemption_id: int, step: str, body: dict | None = None) -> dict:
    """step: start-review | finance-decision | principal-decision | notify-parent"""
    return _request("POST", f"/fee-exemptions/{exemption_id}/{step}", json=body)


def fee_checklist(exemption_id: int, received: list[bool]) -> dict:
    return _request("PUT", f"/fee-exemptions/{exemption_id}/checklist", json={"received": received})


# ---- Week 5: forecasting -------------------------------------------------
def _clean(params: dict) -> dict:
    return {k: v for k, v in params.items() if v not in (None, "", "All")}


def history(start: str | None = None, end: str | None = None, category: str | None = None) -> list[dict]:
    return _request("GET", "/analytics/history", params=_clean({"start": start, "end": end, "category": category}))


def forecast(days: int = 14, category: str | None = None, as_of: str | None = None) -> dict:
    return _request("GET", "/forecast", params=_clean({"days": days, "category": category, "as_of": as_of}))


def workload(days: int = 14, as_of: str | None = None, staff: str | None = None) -> dict:
    return _request("GET", "/forecast/workload", params=_clean({"days": days, "as_of": as_of, "staff": staff}))


def surges(days: int = 30, as_of: str | None = None) -> dict:
    return _request("GET", "/forecast/surges", params=_clean({"days": days, "as_of": as_of}))


def insights(days: int = 14, as_of: str | None = None, staff: str | None = None) -> dict:
    return _request("GET", "/forecast/insights", params=_clean({"days": days, "as_of": as_of, "staff": staff}))


def evaluation(as_of: str | None = None) -> dict:
    return _request("GET", "/forecast/evaluation", params=_clean({"as_of": as_of}))


# ---- Week 6: replies, corrections, audit, risk & compliance ---------------
# Week 7: the logged-in staff member is recorded by the API, so no names are sent.
def draft_reply(ticket_id: int, tone: str) -> dict:
    return _request("POST", f"/tickets/{ticket_id}/responses", json={"tone": tone})


def replies(ticket_id: int) -> list[dict]:
    return _request("GET", f"/tickets/{ticket_id}/responses")


def edit_reply(response_id: int, body: str) -> dict:
    return _request("PATCH", f"/responses/{response_id}", json={"body": body})


def approve_reply(response_id: int) -> dict:
    return _request("POST", f"/responses/{response_id}/approve", json={})


def correct_classification(ticket_id: int, reason: str, category: str | None = None,
                           urgency: str | None = None) -> dict:
    body = {"reason": reason, "category": category, "urgency": urgency}
    return _request("PATCH", f"/tickets/{ticket_id}/classification", json={k: v for k, v in body.items() if v})


def ticket_audit(ticket_id: int) -> list[dict]:
    return _request("GET", f"/tickets/{ticket_id}/audit")


def anonymise(ticket_id: int) -> dict:
    return _request("POST", f"/privacy/tickets/{ticket_id}/anonymise")


def risk_summary(days: int = 30) -> dict:
    return _request("GET", "/risk/summary", params={"days": days})


def risk_report_pdf(days: int = 30) -> bytes:
    """The PDF bytes (not JSON), so this call does not use _request()."""
    try:
        response = requests.get(base_url() + "/risk/report.pdf", params={"days": days},
                                headers=_headers(), timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ApiError(f"Could not reach the SchoolConnect API at {base_url()}.") from exc
    _raise_for(response)
    return response.content


# ---- Weeks 3-4: analytics dashboard and weekly reports --------------------
def analytics_scopes() -> list[dict]:
    return _request("GET", "/analytics/scopes")


def analytics_summary(start: str | None = None, end: str | None = None, scope: str | None = None) -> dict:
    params = {k: v for k, v in {"start": start, "end": end, "scope": scope}.items() if v}
    return _request("GET", "/analytics/summary", params=params)


def analytics_trends(weeks: int = 12, scope: str | None = None) -> dict:
    params = {"weeks": weeks, **({"scope": scope} if scope else {})}
    return _request("GET", "/analytics/trends", params=params)


def report_weeks(count: int = 12) -> list[str]:
    return _request("GET", "/reports/weeks", params={"count": count})


def list_reports(scope: str | None = None) -> list[dict]:
    return _request("GET", "/reports", params={"scope": scope} if scope else None)


def create_report(week_start: str, scope: str) -> dict:
    return _request("POST", "/reports/weekly", json={"week_start": week_start, "scope": scope})


def report_pdf(report_id: int) -> bytes:
    """The PDF bytes (not JSON), so this call does not use _request()."""
    try:
        response = requests.get(f"{base_url()}/reports/{report_id}/pdf", headers=_headers(),
                                timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ApiError(f"Could not reach the SchoolConnect API at {base_url()}.") from exc
    _raise_for(response)
    return response.content
