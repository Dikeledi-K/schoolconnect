"""Week 7: the Streamlit HTTP client sends the login token and turns errors into friendly text.

HTTP is mocked: no server, no internet. CI installs frontend/requirements.txt for these tests.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("requests")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "frontend"))

import api_client  # noqa: E402


def _response(status=200, payload=None):
    r = MagicMock(status_code=status, content=b"{}" if payload is not None else b"")
    r.json.return_value = payload if payload is not None else {}
    return r


@pytest.fixture
def token(monkeypatch):
    state = {"value": "tok-123"}
    monkeypatch.setattr(api_client, "current_token", lambda: state["value"])
    monkeypatch.setattr(api_client, "clear_token", lambda: state.update(value=None))
    monkeypatch.setattr(api_client, "_setting", lambda name, default="": default)
    return state


def test_bearer_token_is_sent(token):
    with patch("requests.request", return_value=_response(200, [])) as request:
        api_client.my_work()
    headers = request.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer tok-123"
    assert request.call_args.args[:2] == ("GET", "http://localhost:8000/workflow/my-work")


def test_no_token_means_no_authorization_header(token):
    token["value"] = None
    with patch("requests.request", return_value=_response(201, {"reference": "SC-1"})) as request:
        api_client.create_ticket("hi", None, None, None)
    assert "Authorization" not in request.call_args.kwargs["headers"]


def test_api_key_is_sent_when_configured(token, monkeypatch):
    monkeypatch.setattr(api_client, "_setting", lambda name, default="": "k" if name == "API_KEY" else default)
    with patch("requests.request", return_value=_response(200, {})) as request:
        api_client.health()
    assert request.call_args.kwargs["headers"]["X-API-Key"] == "k"


def test_expired_login_clears_the_token_and_says_so(token):
    with patch("requests.request", return_value=_response(401, {"detail": "expired"})):
        with pytest.raises(api_client.ApiError, match="log in again"):
            api_client.list_tickets()
    assert token["value"] is None


@pytest.mark.parametrize("status,detail,expected", [
    (403, "Only Principal may do this", "Only Principal may do this"),
    (409, "This reply is already approved", "already approved"),
    (423, "Too many failed logins. Try again in 15 minutes.", "15 minutes"),
    (422, None, "not valid"),
    (500, None, "Something went wrong"),
])
def test_errors_become_friendly_messages(token, status, detail, expected):
    with patch("requests.request", return_value=_response(status, {"detail": detail} if detail else {})):
        with pytest.raises(api_client.ApiError, match=expected) as err:
            api_client.staff_list()
    assert err.value.status == status


def test_unreachable_api(token):
    import requests

    with patch("requests.request", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(api_client.ApiError, match="Could not reach"):
            api_client.health()


def test_approve_and_edit_no_longer_send_names(token):
    with patch("requests.request", return_value=_response(200, {})) as request:
        api_client.approve_reply(5)
        assert request.call_args.kwargs["json"] == {}
        api_client.edit_reply(5, "new text")
        assert request.call_args.kwargs["json"] == {"body": "new text"}


# ---- Weeks 3-4: analytics and weekly reports -------------------------------
def test_report_pdf_download_sends_the_token(token):
    pdf = MagicMock(status_code=200, content=b"%PDF-1.4 test")
    with patch("requests.get", return_value=pdf) as get:
        assert api_client.report_pdf(7) == b"%PDF-1.4 test"
    url, kwargs = get.call_args.args[0], get.call_args.kwargs
    assert url.endswith("/reports/7/pdf") and kwargs["headers"]["Authorization"].startswith("Bearer ")


def test_create_report_and_summary_requests(token):
    with patch("requests.request", return_value=_response(201, {"id": 1})) as request:
        api_client.create_report("2026-03-02", "school")
    assert request.call_args.kwargs["json"] == {"week_start": "2026-03-02", "scope": "school"}
    with patch("requests.request", return_value=_response(200, {"metrics": {}})) as request:
        api_client.analytics_summary(start="2026-03-02", end="2026-03-08")
    assert request.call_args.kwargs["params"] == {"start": "2026-03-02", "end": "2026-03-08"}
