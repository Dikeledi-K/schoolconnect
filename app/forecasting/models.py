"""Four simple forecasting approaches.

Every model has the same shape:
    predict(history, future_dates, cal) -> numpy array of predicted tickets per day

  history      : pd.Series of daily counts, index = dates, ending the day before the forecast starts
  future_dates : pd.DatetimeIndex of the days to forecast
  cal          : calendar flag table (app.forecasting.calendar.calendar_features) covering
                 BOTH the history and the future dates

The first three are "baselines": rules a clerk could do on paper. The fourth is a
machine-learning model. We only trust the ML model when it beats the baselines
in the backtest (see evaluate.py).
"""

import numpy as np
import pandas as pd

from app.forecasting.calendar import FLAG_COLUMNS

MODEL_DESCRIPTIONS = {
    "seasonal_naive": "Same weekday last week. 'Next Monday will look like last Monday.'",
    "last_year": "Same day last year, scaled by how much busier this year is.",
    "moving_average": "Average of recent school days, adjusted for weekday, weekends and holidays.",
    "ml_calendar": "Machine learning (gradient boosting) using school-calendar features "
                   "(term start, admissions window, exams, reports, weekday) and last year's value.",
}
BASELINES = ["seasonal_naive", "last_year", "moving_average"]
ALL_MODELS = BASELINES + ["ml_calendar"]


def seasonal_naive(history: pd.Series, future_dates, cal=None) -> np.ndarray:
    last_week = history.iloc[-7:]
    by_dow = {d.dayofweek: v for d, v in last_week.items()}
    return np.array([float(by_dow.get(d.dayofweek, 0.0)) for d in future_dates])


def _growth(history: pd.Series, window: int = 56) -> float:
    """Ratio of the last `window` days to the same days one year earlier (clipped)."""
    recent = history.iloc[-window:]
    prior_idx = recent.index - pd.Timedelta(days=364)
    prior = history.reindex(prior_idx)
    if prior.isna().any() or prior.sum() == 0:
        return 1.0
    return float(np.clip(recent.sum() / prior.sum(), 0.7, 1.5))


def last_year(history: pd.Series, future_dates, cal=None) -> np.ndarray:
    # 364 days = exactly 52 weeks, so Monday lines up with Monday.
    growth = _growth(history)
    fallback = seasonal_naive(history, future_dates)
    preds = []
    for i, d in enumerate(future_dates):
        prev = d - pd.Timedelta(days=364)
        preds.append(history[prev] * growth if prev in history.index else fallback[i])
    return np.array(preds, dtype=float)


def moving_average(history: pd.Series, future_dates, cal=None) -> np.ndarray:
    """Recent average, adjusted for weekday and for school days vs holidays.

    Without a calendar it falls back to a plain 4-week average with weekday factors.
    """
    recent = history.iloc[-84:]
    if cal is None:
        overall = recent.mean()
        factors = recent.groupby(recent.index.dayofweek).mean() / overall if overall > 0 else None
        level = history.iloc[-28:].mean()
        return np.array([level * (factors.get(d.dayofweek, 1.0) if factors is not None else 1.0)
                         for d in future_dates], dtype=float)

    school = cal.reindex(history.index)["is_school_day"].astype(bool)
    weekend = cal.reindex(history.index)["is_weekend"].astype(bool)
    school_recent = recent[school.reindex(recent.index)]
    level = school_recent.iloc[-20:].mean() if len(school_recent) else recent.mean()
    school_mean = school_recent.mean() if len(school_recent) else 0
    dow = (school_recent.groupby(school_recent.index.dayofweek).mean() / school_mean
           if school_mean > 0 else pd.Series(dtype=float))
    weekend_level = recent[weekend.reindex(recent.index)].mean()
    # How quiet are holiday weekdays compared with school days, over all history?
    holiday_weekdays = history[~school & ~weekend]
    school_all = history[school]
    holiday_ratio = (holiday_weekdays.mean() / school_all.mean()
                     if len(holiday_weekdays) and school_all.mean() > 0 else 0.2)

    preds = []
    for d in future_dates:
        flags = cal.loc[d] if d in cal.index else None
        if flags is not None and flags["is_weekend"]:
            preds.append(weekend_level if not np.isnan(weekend_level) else 0.0)
        elif flags is not None and not flags["is_school_day"]:
            preds.append(level * holiday_ratio)
        else:
            preds.append(level * dow.get(d.dayofweek, 1.0))
    return np.nan_to_num(np.array(preds, dtype=float))


ML_FEATURES = FLAG_COLUMNS + ["day_of_week", "days_since_term_start", "month", "lag_364"]


def _ml_frame(series: pd.Series, dates, cal: pd.DataFrame) -> pd.DataFrame:
    X = cal.reindex(dates)[FLAG_COLUMNS + ["day_of_week", "days_since_term_start"]].copy()
    X["month"] = X.index.month
    # Last year's value for the same weekday; NaN if we have no history that far back.
    X["lag_364"] = series.reindex(X.index - pd.Timedelta(days=364)).to_numpy()
    return X[ML_FEATURES]


def ml_calendar(history: pd.Series, future_dates, cal: pd.DataFrame, seed: int = 0) -> np.ndarray:
    # Week 8: imported here, not at the top, so the API starts ~2 s faster (scikit-learn pulls in
    # scipy). Only computing a forecast needs it; reading a stored forecast does not.
    from sklearn.ensemble import HistGradientBoostingRegressor
    from threadpoolctl import threadpool_limits   # installed with scikit-learn

    if len(history) < 90 or history.sum() == 0:
        return moving_average(history, future_dates, cal)
    # -1 means "no value last year" (before our history started).
    X_train = _ml_frame(history, history.index, cal).fillna(-1)
    # Drop features that never change in the training data; they carry no information.
    useful = [c for c in X_train.columns if X_train[c].nunique() > 1]
    model = HistGradientBoostingRegressor(
        loss="poisson", max_iter=150, learning_rate=0.06, min_samples_leaf=5, random_state=seed
    )
    X_future = _ml_frame(history, future_dates, cal).fillna(-1)
    # One thread: the data is tiny (~700 days), and the API runs each request in a different
    # thread. Letting every thread start its own pool of OpenMP workers made later forecasts
    # about 4x slower on a 2-core machine (idle pools keep the CPUs busy).
    with threadpool_limits(limits=1, user_api="openmp"):
        model.fit(X_train[useful], history.to_numpy())
        return model.predict(X_future[useful])


MODELS = {
    "seasonal_naive": seasonal_naive,
    "last_year": last_year,
    "moving_average": moving_average,
    "ml_calendar": ml_calendar,
}


def predict(model_name: str, history: pd.Series, future_dates, cal) -> np.ndarray:
    """Run a model and make sure the output is never negative."""
    preds = MODELS[model_name](history, future_dates, cal)
    return np.clip(np.nan_to_num(np.asarray(preds, dtype=float)), 0, None)
