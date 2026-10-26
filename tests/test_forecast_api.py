"""Week 5 forecast endpoints, using a temporary database of synthetic history."""

from tests.conftest import DEMO_AS_OF

PARAMS = {"as_of": DEMO_AS_OF, "days": 45}


def test_forecast_needs_history(client):
    # `client` uses an empty in-memory database.
    response = client.get("/forecast")
    assert response.status_code == 409
    assert "history" in response.json()["detail"]


def test_forecast_rows_and_backtest_actuals(history_client):
    fc = history_client.get("/forecast", params={**PARAMS, "category": "total"}).json()
    assert fc["is_backtest"] and fc["as_of"] == DEMO_AS_OF
    assert len(fc["rows"]) == 45
    assert {"forecast", "lower", "upper", "actual", "model"} <= set(fc["rows"][0])
    assert fc["rows"][0]["actual"] is not None   # backtest view includes what really happened
    assert any(e["label"] == "School holiday" for e in fc["calendar_events"])


def test_workload_and_staff_scenario(history_client):
    wl = history_client.get("/forecast/workload", params=PARAMS).json()
    assert wl["daily"] and wl["weekly"] and 0.1 <= wl["planning_buffer"] <= 0.5
    assert "actual_utilisation" in wl["weekly"][0]
    more = history_client.get("/forecast/workload", params={**PARAMS, "staff": "admin_clerk:3"}).json()

    def admin_peak(w):
        return max(r["utilisation"] for r in w["weekly"] if r["role"] == "admin_clerk")

    assert admin_peak(more) < admin_peak(wl)


def test_surges_insights_and_evaluation(history_client):
    assert isinstance(history_client.get("/forecast/surges", params=PARAMS).json()["surges"], list)
    insights = history_client.get("/forecast/insights", params=PARAMS).json()["insights"]
    assert insights[0]["type"] == "summary"
    ev = history_client.get("/forecast/evaluation", params={"as_of": DEMO_AS_OF}).json()
    assert ev["overall"]["wape"] < ev["overall"]["baseline_wape"]
    assert {c["category"] for c in ev["per_category"]} >= {"admissions", "academic"}


def test_history_endpoint(history_client):
    rows = history_client.get("/analytics/history", params={
        "start": "2026-01-12", "end": "2026-01-18", "category": "total"}).json()
    assert len(rows) == 7 and all("total" in r for r in rows)


def test_forecast_validation(history_client):
    assert history_client.get("/forecast", params={"days": 0}).status_code == 422
    assert history_client.get("/forecast", params={"days": 61}).status_code == 422
    assert history_client.get("/forecast", params={"category": "sports"}).status_code == 422
    assert history_client.get("/forecast/workload", params={"staff": "janitor:2"}).status_code == 422


def test_forecast_endpoints_respect_api_key(history_client, set_env):
    set_env(API_KEY="secret")
    assert history_client.get("/forecast/evaluation", params={"as_of": DEMO_AS_OF}).status_code == 401
    ok = history_client.get("/forecast/evaluation", params={"as_of": DEMO_AS_OF},
                            headers={"X-API-Key": "secret"})
    assert ok.status_code == 200


def test_refresh_job_requires_token(history_client, set_env):
    assert history_client.post("/jobs/refresh-forecast").status_code == 503   # jobs disabled
    set_env(JOBS_TOKEN="tok")
    assert history_client.post("/jobs/refresh-forecast").status_code == 401
    assert history_client.post("/jobs/refresh-forecast", headers={"X-Jobs-Token": "wrong"}).status_code == 401
    ok = history_client.post("/jobs/refresh-forecast", headers={"X-Jobs-Token": "tok"}, params={"days": 14})
    assert ok.status_code == 200 and ok.json()["run_id"] >= 1
