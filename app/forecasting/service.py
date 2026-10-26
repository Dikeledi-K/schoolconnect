"""Puts the forecasting pieces together and caches the expensive part.

compute_bundle() is the whole pipeline in one place:
    tickets -> daily counts -> calendar features -> backtest + model choice -> forecast
Endpoints then slice the cached bundle (e.g. 14 days) and add workload, surges and insights.
"""

import threading

import pandas as pd
from sqlalchemy.orm import Session

from app import crud
from app.forecasting.calendar import calendar_features
from app.forecasting.data import SCHOOL_TIMEZONE, daily_counts
from app.forecasting.evaluate import evaluate
from app.forecasting.forecast import MAX_HORIZON, make_forecast
from app.forecasting.insights import build_insights
from app.forecasting.models import MODEL_DESCRIPTIONS
from app.forecasting.surges import find_surges
from app.forecasting.workload import daily_workload, weekly_workload
from app.models import ForecastRun

_cache: dict = {}
_lock = threading.Lock()


class NotEnoughHistory(ValueError):
    pass


def today_local() -> pd.Timestamp:
    return pd.Timestamp.now(tz=SCHOOL_TIMEZONE).tz_localize(None).normalize()


def compute_bundle(rows, as_of=None) -> dict:
    """Run the full pipeline using only tickets created BEFORE as_of."""
    as_of = pd.Timestamp(as_of).normalize() if as_of is not None else today_local()
    all_daily = daily_counts(rows)
    if all_daily.empty or all_daily["total"].sum() == 0:
        raise NotEnoughHistory("no ticket history yet; run scripts/generate_history.py")
    history = all_daily.loc[all_daily.index < as_of]
    if len(history) < 56:
        raise NotEnoughHistory("need at least 8 weeks of ticket history before the forecast date")
    # Make sure history runs right up to the day before as_of (zero-filled).
    history = daily_counts(rows, start=history.index.min(), end=as_of - pd.Timedelta(days=1))
    history = history.loc[history.index < as_of]

    cal = calendar_features(history.index.min(), as_of + pd.Timedelta(days=MAX_HORIZON))
    ev = evaluate(history, cal)
    forecast = make_forecast(history, cal, ev["chosen"], ev["intervals"], days=MAX_HORIZON)

    # If as_of is in the past we can show what really happened (backtest demo view).
    future_actual = all_daily.loc[(all_daily.index >= as_of)
                                  & (all_daily.index < as_of + pd.Timedelta(days=MAX_HORIZON))]
    return {"as_of": as_of, "history": history, "cal": cal, "evaluation": ev,
            "forecast": forecast, "actuals": future_actual}


def get_bundle(db: Session, as_of=None) -> dict:
    """Cached compute_bundle(). The cache resets whenever the ticket count changes."""
    rows = crud.ticket_timestamps(db)
    key = (str(pd.Timestamp(as_of).date()) if as_of else str(today_local().date()), len(rows))
    with _lock:
        if key in _cache:
            return _cache[key]
    bundle = compute_bundle(rows, as_of)
    with _lock:
        if len(_cache) > 8:
            _cache.clear()
        _cache[key] = bundle
    return bundle


def clear_cache():
    with _lock:
        _cache.clear()


# ---------- slices used by the API ----------

def _window(bundle, days: int) -> pd.DataFrame:
    days = max(1, min(int(days), MAX_HORIZON))
    end = bundle["as_of"] + pd.Timedelta(days=days - 1)
    return bundle["forecast"][bundle["forecast"]["date"] <= end]


def forecast_rows(bundle, days=14, category=None) -> list[dict]:
    fc = _window(bundle, days)
    if category:
        fc = fc[fc["category"] == category]
    actuals = bundle["actuals"]
    out = []
    for r in fc.itertuples():
        actual = None
        if r.date in actuals.index:
            actual = int(actuals.loc[r.date, r.category])
        out.append({"date": r.date.date().isoformat(), "category": r.category,
                    "forecast": round(r.forecast, 2), "lower": round(r.lower, 2),
                    "upper": round(r.upper, 2), "model": r.model, "actual": actual})
    return out


def planning_buffer(bundle) -> float:
    """Busy-week margin = the system's average backtest error (WAPE), capped at 50%."""
    wape = bundle["evaluation"]["overall"]["wape"]
    return float(min(0.5, max(0.1, wape)))


def workload(bundle, days=14, staff_override=None):
    fc = _window(bundle, days)
    daily = daily_workload(fc, bundle["cal"], staff_override, buffer=planning_buffer(bundle))
    weekly = weekly_workload(daily)
    # Backtest view: if the forecast window is in the past, add what the workload REALLY was.
    actuals = bundle["actuals"]
    window_dates = sorted(fc["date"].unique())
    if len(actuals) and not weekly.empty and all(d in actuals.index for d in window_dates):
        act = (actuals.loc[window_dates].drop(columns="total").reset_index()
               .melt(id_vars="date", var_name="category", value_name="forecast"))
        act_weekly = weekly_workload(daily_workload(act, bundle["cal"], staff_override))
        weekly = weekly.merge(act_weekly[["week_start", "role", "utilisation"]]
                              .rename(columns={"utilisation": "actual_utilisation"}),
                              on=["week_start", "role"], how="left")
    return daily, weekly


def surges(bundle, days=30) -> list[dict]:
    return find_surges(_window(bundle, days), bundle["history"], bundle["cal"])


def last_year_total(bundle, days) -> float | None:
    dates = pd.date_range(bundle["as_of"], periods=days, freq="D") - pd.Timedelta(days=364)
    prev = bundle["history"].reindex(dates)["total"]
    return None if prev.isna().any() or prev.sum() == 0 else float(prev.sum())


def insights(bundle, days=14, staff_override=None) -> list[dict]:
    _, weekly = workload(bundle, days, staff_override)
    return build_insights(_window(bundle, days), weekly, surges(bundle, days),
                          last_year_total(bundle, days), days)


def evaluation_summary(bundle) -> dict:
    ev = bundle["evaluation"]
    table = ev["metrics"]
    per_category = []
    for cat in sorted(table["category"].unique()):  # (the "total" band is reported in overall)
        sub = table[table["category"] == cat].set_index("model")
        per_category.append({
            "category": cat,
            "chosen_model": ev["chosen"][cat],
            "models": {m: {"mae": round(r["mae"], 2),
                           "wape": None if pd.isna(r["wape"]) else round(r["wape"], 3)}
                       for m, r in sub.iterrows()},
            "interval": [round(x, 2) for x in ev["intervals"][cat]],
        })
    overall = {**ev["overall"], "total_interval": [round(x, 2) for x in ev["intervals"]["total"]]}
    return {"as_of": bundle["as_of"].date().isoformat(), "overall": overall,
            "per_category": per_category, "model_descriptions": MODEL_DESCRIPTIONS}


def history_rows(bundle_or_daily, start=None, end=None, category=None) -> list[dict]:
    daily = bundle_or_daily
    if start:
        daily = daily.loc[daily.index >= pd.Timestamp(start)]
    if end:
        daily = daily.loc[daily.index <= pd.Timestamp(end)]
    cols = [category] if category else list(daily.columns)
    return [{"date": d.date().isoformat(), **{c: int(row[c]) for c in cols}} for d, row in daily.iterrows()]


def calendar_events(bundle, start, end) -> list[dict]:
    """Shaded periods for charts: holidays, exams, admissions windows, report windows."""
    cal = bundle["cal"]
    cal = cal.loc[(cal.index >= pd.Timestamp(start)) & (cal.index <= pd.Timestamp(end))]
    events = []
    for col, label in [("is_holiday_break", "School holiday"), ("exam_period", "Exams"),
                       ("admissions_window", "Admissions window")]:
        run_start = None
        for d, v in cal[col].items():
            if v and run_start is None:
                run_start = d
            if not v and run_start is not None:
                events.append({"type": col, "label": label, "start": run_start.date().isoformat(),
                               "end": (d - pd.Timedelta(days=1)).date().isoformat()})
                run_start = None
        if run_start is not None:
            events.append({"type": col, "label": label, "start": run_start.date().isoformat(),
                           "end": cal.index.max().date().isoformat()})
    return events


def save_run(db: Session, bundle, days=60) -> ForecastRun:
    ev = bundle["evaluation"]
    run = ForecastRun(
        as_of=bundle["as_of"].date().isoformat(),
        horizon_days=days,
        chosen_models=ev["chosen"],
        metrics=evaluation_summary(bundle),
        forecast=forecast_rows(bundle, days),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
