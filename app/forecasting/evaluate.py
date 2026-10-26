"""Backtesting: how accurate would each model have been in the recent past?

We pretend it is an earlier date, forecast the next 14 days using ONLY data from
before that date, then compare with what actually happened. We repeat this for
4 starting points covering the last 8 weeks ("rolling-origin backtest").

Metrics:
  MAE  – mean absolute error: on average, how many tickets per day we were off by.
  WAPE – weighted absolute percentage error: total error / total actual tickets.
         0.20 means "20% off overall". Lower is better.
"""

import numpy as np
import pandas as pd

from app.forecasting.models import ALL_MODELS, BASELINES, predict
from app.forecasting.data import CATEGORY_KEYS

# ML must be at least this much better (relative WAPE) than the best baseline to be used.
ML_MIN_IMPROVEMENT = 0.02


def backtest_origins(last_day: pd.Timestamp, n_origins: int = 4, step: int = 14, horizon: int = 14):
    """Forecast start dates so the final test window ends on last_day."""
    last_origin = last_day - pd.Timedelta(days=horizon - 1)
    return [last_origin - pd.Timedelta(days=step * k) for k in reversed(range(n_origins))]


def rolling_backtest(daily: pd.DataFrame, cal: pd.DataFrame, categories=None, models=None,
                     n_origins: int = 4, step: int = 14, horizon: int = 14) -> pd.DataFrame:
    """One row per (category, model, origin, date) with actual and predicted counts.

    Leakage rule: for each origin, models only ever see history strictly BEFORE the origin.
    """
    categories = categories or CATEGORY_KEYS
    models = models or ALL_MODELS
    rows = []
    for origin in backtest_origins(daily.index.max(), n_origins, step, horizon):
        train = daily.loc[daily.index < origin]
        test_dates = pd.date_range(origin, periods=horizon, freq="D")
        test_dates = test_dates[test_dates <= daily.index.max()]
        if len(train) < 28 or len(test_dates) == 0:
            continue
        for cat in categories:
            actual = daily.loc[test_dates, cat].to_numpy()
            for m in models:
                preds = predict(m, train[cat], test_dates, cal)
                for d, a, p in zip(test_dates, actual, preds):
                    rows.append({"category": cat, "model": m, "origin": origin, "date": d,
                                 "actual": float(a), "pred": float(p),
                                 "train_end": train.index.max()})
    return pd.DataFrame(rows)


def _wape(actual, pred) -> float:
    total = np.sum(actual)
    return float(np.sum(np.abs(actual - pred)) / total) if total > 0 else float("nan")


def metrics_table(results: pd.DataFrame) -> pd.DataFrame:
    """MAE and WAPE per (category, model)."""
    g = results.groupby(["category", "model"])
    out = g.apply(lambda df: pd.Series({
        "mae": float(np.mean(np.abs(df["actual"] - df["pred"]))),
        "wape": _wape(df["actual"].to_numpy(), df["pred"].to_numpy()),
        "days": len(df),
    }), include_groups=False).reset_index()
    return out


def choose_model(cat_metrics: pd.DataFrame) -> str:
    """Pick the model for one category.

    Rule: take the best baseline. Only switch to the ML model if its WAPE is at least
    ML_MIN_IMPROVEMENT better. A complicated model must earn its place.
    """
    m = cat_metrics.set_index("model")["wape"].fillna(np.inf)
    baselines = m.reindex(BASELINES).dropna()
    best_baseline = baselines.idxmin() if len(baselines) else "moving_average"
    if "ml_calendar" in m and m["ml_calendar"] < m[best_baseline] * (1 - ML_MIN_IMPROVEMENT):
        return "ml_calendar"
    return best_baseline


def interval_ratios(results: pd.DataFrame, category: str, model: str,
                    low_q: float = 0.10, high_q: float = 0.90) -> tuple[float, float]:
    """80% band as multipliers of the forecast, learned from backtest errors.

    Example: (0.7, 1.4) means "actual tickets were usually between 70% and 140% of the forecast".
    """
    df = results[(results["category"] == category) & (results["model"] == model) & (results["pred"] >= 1)]
    if len(df) < 10:
        return 0.6, 1.4
    ratio = df["actual"] / df["pred"]
    return float(np.clip(ratio.quantile(low_q), 0, 1)), float(max(1.0, ratio.quantile(high_q)))


def evaluate(daily: pd.DataFrame, cal: pd.DataFrame, **kwargs) -> dict:
    """Run the backtest and return chosen models, metrics and interval ratios."""
    results = rolling_backtest(daily, cal, **kwargs)
    if results.empty:
        raise ValueError("not enough history to backtest (need at least ~6 weeks)")
    table = metrics_table(results)

    chosen, intervals = {}, {}
    for cat in table["category"].unique():
        chosen[cat] = choose_model(table[table["category"] == cat])
        intervals[cat] = interval_ratios(results, cat, chosen[cat])

    # Overall accuracy of the system: sum of the chosen per-category forecasts vs actual total.
    picked = pd.concat([results[(results["category"] == c) & (results["model"] == m)]
                        for c, m in chosen.items()])
    total = picked.groupby("date")[["actual", "pred"]].sum()
    baseline_total = (results[results["model"] == "seasonal_naive"]
                      .groupby("date")[["actual", "pred"]].sum())
    # Band for the TOTAL, learned directly from total errors (summing category bands overstates it).
    tot = total[total["pred"] >= 1]
    ratio = tot["actual"] / tot["pred"]
    intervals["total"] = ((float(np.clip(ratio.quantile(0.10), 0, 1)), float(max(1.0, ratio.quantile(0.90))))
                          if len(tot) >= 10 else (0.7, 1.3))
    overall = {
        "mae": float(np.mean(np.abs(total["actual"] - total["pred"]))),
        "wape": _wape(total["actual"].to_numpy(), total["pred"].to_numpy()),
        "baseline_wape": _wape(baseline_total["actual"].to_numpy(), baseline_total["pred"].to_numpy()),
        "days_tested": int(total.shape[0]),
        "test_start": str(results["date"].min().date()),
        "test_end": str(results["date"].max().date()),
    }
    return {"chosen": chosen, "intervals": intervals, "metrics": table, "overall": overall,
            "results": results}
