"""Forecast the next N days per category using the model chosen in the backtest."""

import pandas as pd

from app.forecasting.data import CATEGORY_KEYS
from app.forecasting.models import predict

MAX_HORIZON = 60


def make_forecast(daily: pd.DataFrame, cal: pd.DataFrame, chosen: dict, intervals: dict,
                  days: int = 14) -> pd.DataFrame:
    """Rows: date, category, forecast, lower, upper, model. Includes a "total" category.

    daily must end the day before the forecast starts.
    """
    days = max(1, min(int(days), MAX_HORIZON))
    start = daily.index.max() + pd.Timedelta(days=1)
    future = pd.date_range(start, periods=days, freq="D")

    rows = []
    for cat in CATEGORY_KEYS:
        model = chosen.get(cat, "moving_average")
        low, high = intervals.get(cat, (0.6, 1.4))
        preds = predict(model, daily[cat], future, cal)
        for d, p in zip(future, preds):
            rows.append({"date": d, "category": cat, "forecast": float(p),
                         "lower": float(p * low), "upper": float(p * high), "model": model})
    df = pd.DataFrame(rows)

    total = df.groupby("date")[["forecast"]].sum().reset_index()
    # The total has its own band from the backtest; summing category bands would overstate it.
    low, high = intervals.get("total", (0.7, 1.3))
    total["lower"], total["upper"] = total["forecast"] * low, total["forecast"] * high
    total["category"] = "total"
    total["model"] = "sum of categories"
    return pd.concat([df, total], ignore_index=True)
