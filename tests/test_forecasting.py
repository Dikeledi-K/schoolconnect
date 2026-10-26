"""Week 5: calendar, data prep, models, backtest, workload, surges and insights."""

from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest

from app.forecasting import evaluate as ev
from app.forecasting.calendar import calendar_features
from app.forecasting.data import CATEGORY_KEYS, daily_counts
from app.forecasting.forecast import make_forecast
from app.forecasting.insights import build_insights
from app.forecasting.models import ALL_MODELS, predict
from app.forecasting.surges import find_surges
from app.forecasting.workload import daily_workload, weekly_workload
from app.synthetic import expected_rates, generate_tickets

CFG = {
    "handling_minutes": {c: 30 for c in CATEGORY_KEYS},
    "staff": {"admin_clerk": 1, "finance_clerk": 1, "class_teacher": 1, "deputy_principal": 1, "it_support": 1},
    "hours_per_day": {"admin_clerk": 4, "finance_clerk": 4, "class_teacher": 1, "deputy_principal": 2, "it_support": 4},
    "holiday_capacity_factor": 0.5, "busy_threshold": 0.8, "overload_threshold": 1.0,
}


# ---------------------------------------------------------------- calendar
def test_calendar_flags_known_dates():
    cal = calendar_features("2026-01-01", "2026-12-31")
    assert cal.loc["2026-01-01", "is_public_holiday"] == 1
    assert cal.loc["2026-01-14", "is_school_day"] == 1           # term 1 starts
    assert cal.loc["2026-01-14", "school_year_start"] == 1
    assert cal.loc["2026-01-09", "pre_term_week"] == 1
    assert cal.loc["2026-01-05", "is_holiday_break"] == 1
    assert cal.loc["2026-07-28", "admissions_window"] == 1
    assert cal.loc["2026-11-10", "exam_period"] == 1
    assert cal.loc["2026-01-17", "is_weekend"] == 1 and cal.loc["2026-01-17", "is_school_day"] == 0
    assert cal.loc["2026-12-10", "report_window"] == 1          # day after report day


# ---------------------------------------------------------------- data
def test_daily_counts_zero_fills_and_uses_local_time():
    rows = [
        (datetime(2026, 3, 2, 21, 30), "academic"),                          # naive = UTC -> 23:30 SAST, same day
        (datetime(2026, 3, 2, 22, 30, tzinfo=timezone.utc), "academic"),     # 00:30 SAST next day
        (datetime(2026, 3, 5, 8, 0, tzinfo=timezone.utc), "fees_exemptions"),
    ]
    d = daily_counts(rows)
    assert list(d.index.strftime("%Y-%m-%d")) == ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05"]
    assert d.loc["2026-03-02", "academic"] == 1 and d.loc["2026-03-03", "academic"] == 1
    assert d.loc["2026-03-04", "total"] == 0                                # zero-filled
    assert set(CATEGORY_KEYS) <= set(d.columns)


# ---------------------------------------------------------------- synthetic data
def test_synthetic_history_is_reproducible_and_seasonal():
    a = generate_tickets("2025-01-01", "2025-02-28", seed=1)
    b = generate_tickets("2025-01-01", "2025-02-28", seed=1)
    assert len(a) == len(b) and a[0]["message"] == b[0]["message"]
    rates = expected_rates("2025-01-01", "2025-12-31")
    jan_opening = rates.loc["2025-01-20", "admissions"]
    july_holiday = rates.loc["2025-07-02", "admissions"]
    assert jan_opening > 5 * july_holiday
    assert all(t["parent_name"] is None and t["parent_contact"] is None for t in a)  # no personal data
    assert len({t["reference"] for t in a}) == len(a) and a[0]["reference"].endswith("-0001")


# ---------------------------------------------------------------- models
@pytest.fixture(scope="module")
def series():
    cal = calendar_features("2024-11-01", "2026-03-31")
    rates = expected_rates("2024-11-01", "2026-03-31")
    rng = np.random.default_rng(0)
    daily = pd.DataFrame(rng.poisson(rates), index=rates.index, columns=rates.columns)
    daily["total"] = daily[CATEGORY_KEYS].sum(axis=1)
    return daily, cal


@pytest.mark.parametrize("model", ALL_MODELS)
def test_models_return_right_shape_and_non_negative(series, model):
    daily, cal = series
    hist = daily.loc[:"2025-12-14", "admissions"]
    future = pd.date_range("2025-12-15", periods=30, freq="D")
    preds = predict(model, hist, future, cal)
    assert preds.shape == (30,) and (preds >= 0).all() and np.isfinite(preds).all()


def test_ml_model_learns_the_january_rush(series):
    daily, cal = series
    hist = daily.loc[:"2025-12-14", "admissions"]
    future = pd.date_range("2025-12-15", periods=45, freq="D")
    preds = pd.Series(predict("ml_calendar", hist, future, cal), index=future)
    assert preds["2026-01-19":"2026-01-23"].mean() > 3 * preds["2025-12-22":"2025-12-24"].mean()


def test_seasonal_naive_repeats_last_week():
    idx = pd.date_range("2026-03-02", periods=14, freq="D")
    hist = pd.Series(range(14), index=idx, dtype=float)
    preds = predict("seasonal_naive", hist, pd.date_range("2026-03-16", periods=7, freq="D"), None)
    assert list(preds) == [7, 8, 9, 10, 11, 12, 13]


# ---------------------------------------------------------------- backtest
def test_backtest_has_no_data_leakage(series):
    daily, cal = series
    res = ev.rolling_backtest(daily.loc[:"2025-11-30"], cal, categories=["academic"], models=["seasonal_naive"])
    assert not res.empty
    assert (res["train_end"] < res["origin"]).all()
    assert (res["date"] >= res["origin"]).all()
    assert res["origin"].nunique() == 4 and res["date"].max() == pd.Timestamp("2025-11-30")


def test_ml_only_chosen_when_it_beats_baseline():
    m = lambda wapes: pd.DataFrame({"model": list(wapes), "wape": list(wapes.values())})  # noqa: E731
    assert ev.choose_model(m({"seasonal_naive": .5, "last_year": .4, "moving_average": .45, "ml_calendar": .30})) == "ml_calendar"
    # ML is a hair better but not by the 2% margin: keep the simple baseline.
    assert ev.choose_model(m({"seasonal_naive": .5, "last_year": .40, "moving_average": .45, "ml_calendar": .399})) == "last_year"
    assert ev.choose_model(m({"seasonal_naive": .3, "last_year": .4, "moving_average": .45, "ml_calendar": .35})) == "seasonal_naive"


def test_pipeline_beats_simple_baseline(demo_bundle):
    overall = demo_bundle["evaluation"]["overall"]
    assert overall["wape"] < overall["baseline_wape"]


def test_forecast_band_contains_forecast(demo_bundle):
    fc = demo_bundle["forecast"]
    assert (fc["lower"] <= fc["forecast"] + 1e-9).all() and (fc["upper"] >= fc["forecast"] - 1e-9).all()
    assert set(fc["category"]) == set(CATEGORY_KEYS) | {"total"}


def test_january_backtest_is_reasonably_accurate(demo_bundle):
    fc = demo_bundle["forecast"]
    total = fc[fc["category"] == "total"].set_index("date")["forecast"]["2026-01-12":"2026-01-30"]
    actual = demo_bundle["actuals"]["total"]["2026-01-12":"2026-01-30"]
    wape = (total - actual).abs().sum() / actual.sum()
    assert wape < 0.35


# ---------------------------------------------------------------- workload
def _fc(rows):
    return pd.DataFrame([{"date": pd.Timestamp(d), "category": c, "forecast": f, "lower": f, "upper": f}
                         for d, c, f in rows])


def test_workload_maths():
    cal = calendar_features("2026-03-02", "2026-03-08")
    # Monday: 8 admissions tickets x 30 min = 4 hours for the admin clerk (capacity 4h) -> 100%.
    fc = _fc([("2026-03-02", "admissions", 8.0), ("2026-03-02", "fees_exemptions", 10.0)])
    d = daily_workload(fc, cal, cfg=CFG).set_index("role")
    assert d.loc["admin_clerk", "hours_needed"] == pytest.approx(4.0)
    assert d.loc["admin_clerk", "utilisation"] == pytest.approx(1.0)
    assert d.loc["admin_clerk", "status"] == "busy"
    assert d.loc["finance_clerk", "utilisation"] == pytest.approx(1.25)
    assert d.loc["finance_clerk", "status"] == "overloaded"


def test_staff_scenario_and_weekend_carry_over():
    cal = calendar_features("2026-03-06", "2026-03-09")  # Fri..Mon
    fc = _fc([("2026-03-07", "admissions", 4.0), ("2026-03-09", "admissions", 4.0)])
    d = daily_workload(fc, cal, staff_override={"admin_clerk": 2}, cfg=CFG)
    mon = d[(d["role"] == "admin_clerk") & (d["date"] == "2026-03-09")].iloc[0]
    assert mon["hours_needed"] == pytest.approx(4.0)     # Saturday's tickets land on Monday
    assert mon["capacity_hours"] == pytest.approx(8.0)   # 2 clerks x 4h
    assert pd.Timestamp("2026-03-07") not in set(d["date"])
    w = weekly_workload(d, cfg=CFG)
    assert set(w.columns) >= {"utilisation", "utilisation_upper", "overload_risk"}


# ---------------------------------------------------------------- surges
def test_surge_detection_flags_planted_spike():
    idx = pd.date_range("2026-02-02", "2026-03-08", freq="D")
    daily = pd.DataFrame(0, index=idx, columns=CATEGORY_KEYS)
    daily.loc[idx.dayofweek < 5, "academic"] = 10
    daily["total"] = daily[CATEGORY_KEYS].sum(axis=1)
    cal = calendar_features("2026-02-02", "2026-03-20")
    future = pd.date_range("2026-03-09", periods=5, freq="D")
    rows = [(d, c, 10.0 if c == "academic" else 0.0) for d in future for c in CATEGORY_KEYS]
    rows = [(d, "academic", 30.0) if (d == pd.Timestamp("2026-03-11") and c == "academic") else (d, c, f)
            for d, c, f in rows]
    surges = find_surges(_fc(rows), daily, cal, cfg=CFG)
    assert [s["date"] for s in surges] == ["2026-03-11"]
    assert surges[0]["main_category"] == "academic"
    assert surges[0]["extra_staff_hours"] == pytest.approx(10.0)  # 20 extra tickets x 30 min


# ---------------------------------------------------------------- insights
def test_insights_name_the_overloaded_role_and_week():
    fc = _fc([("2026-01-19", "admissions", 20.0)])
    weekly = pd.DataFrame([{
        "week_start": pd.Timestamp("2026-01-19"), "role": "admin_clerk", "role_name": "Admin Clerk",
        "tickets": 20.0, "hours_needed": 10.0, "hours_upper": 12.0, "capacity_hours": 8.0,
        "utilisation": 1.25, "utilisation_upper": 1.5, "status": "overloaded", "overload_risk": False}])
    out = build_insights(fc, weekly, [], last_year_total=10.0, days=14)
    text = " ".join(i["text"] for i in out)
    assert "Admin Clerk" in text and "19 Jan 2026" in text and "125%" in text and "admissions" in text


def test_make_forecast_horizon_is_capped(demo_bundle):
    b = demo_bundle
    fc = make_forecast(b["history"], b["cal"], b["evaluation"]["chosen"], b["evaluation"]["intervals"], days=500)
    assert fc["date"].nunique() == 60
