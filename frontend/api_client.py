"""Tiny HTTP client for the SchoolConnect API. The ONLY way the frontend talks to the backend.

Configuration (first match wins):
1. Streamlit secrets (.streamlit/secrets.toml or Streamlit Cloud settings): API_BASE_URL, API_KEY
2. Environment variables with the same names
3. Default: http://localhost:8000, no key
"""

from __future__ import annotations

import os

import requests
import streamlit as st

TIMEOUT_SECONDS = 60  # the first (uncached) forecast takes a few seconds


class ApiError(Exception):
    """A friendly error message the pages can show to the user."""


def _setting(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001 - no secrets file is fine
        pass
    return os.getenv(name, default)


def base_url() -> str:
    return _setting("API_BASE_URL", "http://localhost:8000").rstrip("/")


def _headers() -> dict:
    key = _setting("API_KEY")
    return {"X-API-Key": key} if key else {}


def _request(method: str, path: str, **kwargs):
    try:
        response = requests.request(
            method, base_url() + path, headers=_headers(), timeout=TIMEOUT_SECONDS, **kwargs
        )
    except requests.RequestException as exc:
        raise ApiError(
            f"Could not reach the SchoolConnect API at {base_url()}. Is it running?"
        ) from exc

    if response.status_code == 401:
        raise ApiError("The API rejected the request: check API_KEY in the frontend settings.")
    if response.status_code == 404:
        raise ApiError("Not found.")
    if response.status_code == 409:
        # e.g. "no ticket history yet" from the forecasting endpoints
        raise ApiError(str(response.json().get("detail", "Not enough data yet.")))
    if response.status_code == 422:
        raise ApiError("Some of the information entered is not valid. Please check and try again.")
    if response.status_code >= 400:
        raise ApiError(f"The API returned an error ({response.status_code}). Please try again.")
    return response.json()


# ---- Endpoints -----------------------------------------------------------
def health() -> dict:
    return _request("GET", "/health")


@st.cache_data(ttl=300)
def taxonomy() -> dict:
    """Cached for 5 minutes: the taxonomy rarely changes."""
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
def draft_reply(ticket_id: int, tone: str) -> dict:
    return _request("POST", f"/tickets/{ticket_id}/responses", json={"tone": tone})


def replies(ticket_id: int) -> list[dict]:
    return _request("GET", f"/tickets/{ticket_id}/responses")


def edit_reply(response_id: int, body: str, actor: str) -> dict:
    return _request("PATCH", f"/responses/{response_id}", json={"body": body, "actor": actor})


def approve_reply(response_id: int, approved_by: str) -> dict:
    return _request("POST", f"/responses/{response_id}/approve", json={"approved_by": approved_by})


def correct_classification(ticket_id: int, actor: str, reason: str,
                           category: str | None = None, urgency: str | None = None) -> dict:
    body = {"actor": actor, "reason": reason, "category": category, "urgency": urgency}
    return _request("PATCH", f"/tickets/{ticket_id}/classification", json={k: v for k, v in body.items() if v})


def ticket_audit(ticket_id: int) -> list[dict]:
    return _request("GET", f"/tickets/{ticket_id}/audit")


def anonymise(ticket_id: int, actor: str) -> dict:
    return _request("POST", f"/privacy/tickets/{ticket_id}/anonymise", params={"actor": actor})


def risk_summary(days: int = 30) -> dict:
    return _request("GET", "/risk/summary", params={"days": days})


def risk_report_pdf(days: int = 30) -> bytes:
    """The PDF bytes (not JSON), so this call does not use _request()."""
    try:
        response = requests.get(base_url() + "/risk/report.pdf", params={"days": days},
                                headers=_headers(), timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ApiError(f"Could not reach the SchoolConnect API at {base_url()}.") from exc
    if response.status_code >= 400:
        raise ApiError(f"Could not create the report ({response.status_code}).")
    return response.content
