"""Week 8: stored forecasts. Same answers as computing live, never from tampered or stale data."""

import copy

import pandas as pd
import pytest

from app.forecasting import service as fc
from app.models import StoredForecast
from tests.conftest import DEMO_AS_OF

PARAMS = {"as_of": DEMO_AS_OF, "days": 45}
ENDPOINTS = ["/forecast", "/forecast/workload", "/forecast/surges", "/forecast/insights", "/forecast/evaluation"]


@pytest.fixture
def signed(set_env):
    set_env(JOBS_TOKEN="test-jobs-token")


@pytest.fixture
def db(history_sessionmaker):
    session = history_sessionmaker()
    yield session
    session.query(StoredForecast).delete()     # leave the shared history database as we found it
    session.commit()
    session.close()
    fc.clear_cache()


def _inputs(db, as_of=DEMO_AS_OF):
    when = pd.Timestamp(as_of)
    all_daily, history = fc.history_for(fc.crud.ticket_timestamps(db), when)
    return when, history, all_daily


def test_stored_bundle_gives_identical_results(db, signed, demo_bundle):
    assert fc.store_bundle(db, demo_bundle) is not None
    loaded = fc.load_stored(db, *_inputs(db))
    assert loaded is not None and loaded is not demo_bundle
    assert fc.forecast_rows(loaded, 45) == fc.forecast_rows(demo_bundle, 45)
    assert fc.surges(loaded, 45) == fc.surges(demo_bundle, 45)
    assert fc.insights(loaded, 45) == fc.insights(demo_bundle, 45)
    assert fc.evaluation_summary(loaded) == fc.evaluation_summary(demo_bundle)
    pd.testing.assert_frame_equal(fc.workload(loaded, 45)[1], fc.workload(demo_bundle, 45)[1])


def test_endpoints_answer_from_the_stored_result_without_computing(history_client, db, signed, demo_bundle,
                                                                   monkeypatch):
    fc.store_bundle(db, demo_bundle)
    fc.clear_cache()
    computed = {}
    monkeypatch.setattr(fc, "compute_bundle", lambda *a, **k: pytest.fail("computed instead of loading"))
    for path in ENDPOINTS:
        r = history_client.get(path, params={"as_of": DEMO_AS_OF} if path.endswith("evaluation") else PARAMS)
        assert r.status_code == 200, (path, r.text)
        computed[path] = r.json()
    monkeypatch.undo()
    # Same requests computed live from scratch give exactly the same answers.
    db.query(StoredForecast).delete()
    db.commit()
    fc.clear_cache()
    for path in ENDPOINTS:
        r = history_client.get(path, params={"as_of": DEMO_AS_OF} if path.endswith("evaluation") else PARAMS)
        assert r.json() == computed[path], path


def test_tampered_payload_is_never_unpickled(db, signed, demo_bundle):
    row = fc.store_bundle(db, demo_bundle)
    row.payload = row.payload[:-1] + bytes([row.payload[-1] ^ 1])
    db.commit()
    assert fc.load_stored(db, *_inputs(db)) is None


def test_different_data_or_libraries_are_not_used(db, signed, demo_bundle, monkeypatch):
    fc.store_bundle(db, demo_bundle)
    when, history, all_daily = _inputs(db)
    changed = history.copy()
    changed.iloc[-1, 0] += 1                                   # one more ticket on the last day
    assert fc.load_stored(db, when, changed, all_daily) is None
    monkeypatch.setattr(fc, "library_versions", lambda: "py3.11-pandas9.9")
    assert fc.load_stored(db, when, history, all_daily) is None


def test_nothing_is_stored_or_loaded_without_a_signing_key(db, demo_bundle, set_env):
    set_env(JOBS_TOKEN="")
    assert fc.store_bundle(db, demo_bundle) is None
    assert db.query(StoredForecast).count() == 0


def test_refresh_stores_today_and_the_pinned_dates(db, signed, set_env, demo_bundle, monkeypatch):
    set_env(JOBS_TOKEN="test-jobs-token", FORECAST_PINNED_DATES="2025-12-15, 2026-01-12")

    def fake_compute(rows, as_of=None):          # the real pipeline is tested above; keep this fast
        bundle = copy.copy(demo_bundle)
        bundle["as_of"] = fc._as_of(as_of)
        return bundle

    monkeypatch.setattr(fc, "compute_bundle", fake_compute)
    monkeypatch.setattr(fc, "today_local", lambda: pd.Timestamp("2026-01-20"))
    done = fc.refresh_stored(db)
    assert [d["as_of"] for d in done] == ["2026-01-20", "2025-12-15", "2026-01-12"]
    assert all(d["stored"] for d in done)
    assert sorted(r.as_of for r in db.query(StoredForecast)) == ["2025-12-15", "2026-01-12", "2026-01-20"]
    fc.refresh_stored(db)                         # running it again keeps one row per date
    assert db.query(StoredForecast).count() == 3
