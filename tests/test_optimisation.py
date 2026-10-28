"""Week 8: the speed-ups give exactly the same answers as before."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.forecasting import service as fc
from app.forecasting.workload import daily_workload, load_workload
from app.risk import fairness
from app.taxonomy import CATEGORIES, STAFF_ROLES

ROOT = Path(__file__).resolve().parent.parent


def _reference_hours(forecast: pd.DataFrame) -> dict:
    """The pre-Week-8 way: look every value up in the pandas table (slow, but obviously right)."""
    cfg = load_workload()
    fc_ = forecast[forecast["category"] != "total"].copy()
    fc_["role"] = fc_["category"].map(lambda c: CATEGORIES[c].routed_role)
    fc_["hours"] = fc_["forecast"] * fc_["category"].map(cfg["handling_minutes"]) / 60
    per_day = fc_.groupby(["date", "role"])[["hours"]].sum().unstack("role", fill_value=0)
    return {(role, d): (per_day["hours"][role][d] if role in per_day["hours"].columns else 0.0)
            for d in sorted(fc_["date"].unique()) for role in STAFF_ROLES}


def test_fast_workload_lookup_matches_the_pandas_lookup(demo_bundle):
    window = fc._window(demo_bundle, 45)
    daily = daily_workload(window, demo_bundle["cal"])
    reference = _reference_hours(window)
    # On office days with nothing carried over from a weekend, hours needed = that day's hours.
    weekdays = daily[daily["date"].dt.dayofweek.between(1, 4)]       # Tue-Fri: no weekend carry-over
    holidays = set(demo_bundle["cal"].index[demo_bundle["cal"]["is_public_holiday"] == 1])
    checked = 0
    for row in weekdays.itertuples():
        prev = row.date - pd.Timedelta(days=1)
        if prev in holidays:
            continue
        assert row.hours_needed == pytest.approx(reference[(row.role, row.date)], abs=1e-12)
        checked += 1
    assert checked > 50


def test_classifier_fairness_is_cached_but_cannot_be_changed_by_callers():
    first = fairness.classifier_fairness()
    first["overall_accuracy"] = -1
    first["by_language"].clear()
    again = fairness.classifier_fairness()
    assert again["overall_accuracy"] > 0.9 and again["by_language"]
    assert fairness._classifier_fairness.cache_info().hits >= 1


def test_the_api_starts_without_loading_scikit_learn():
    code = "import sys, app.main; print('sklearn' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                         env={**__import__("os").environ, "DATABASE_URL": "sqlite://"})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


def test_frontend_cache_is_per_login():
    pytest.importorskip("streamlit")
    sys.path.insert(0, str(ROOT / "frontend"))
    import api_client

    api_client._cached_get.clear()
    reply = MagicMock(status_code=200, content=b"[]")
    reply.json.return_value = []
    who = {"token": "alice"}
    with patch.object(api_client, "current_token", lambda: who["token"]), \
            patch.object(api_client, "_setting", lambda name, default="": default), \
            patch("requests.request", return_value=reply) as request:
        api_client.staff_list()     # alice: asks the API
        api_client.staff_list()     # alice again: from the cache
        who["token"] = "bob"
        api_client.staff_list()     # bob: never sees alice's cached answer
    assert request.call_count == 2
    assert request.call_args.kwargs["headers"]["Authorization"] == "Bearer bob"
