"""Finds days where the forecast is far above what is normal recently."""

import pandas as pd

from app.forecasting.calendar import describe_day
from app.forecasting.data import CATEGORY_KEYS
from app.forecasting.workload import load_workload
from app.taxonomy import CATEGORIES

SURGE_FACTOR = 1.5      # forecast must be at least 1.5x the typical level...
MIN_EXTRA_TICKETS = 5   # ...and at least 5 tickets above it
TYPICAL_FLOOR = 5.0     # avoid "surges" measured against an almost-empty holiday


def typical_levels(daily: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """Median tickets per weekday over the last 4 weeks (public holidays excluded)."""
    recent = daily.iloc[-28:]
    recent = recent[~cal.reindex(recent.index)["is_public_holiday"].astype(bool)]
    return recent.groupby(recent.index.dayofweek)[CATEGORY_KEYS + ["total"]].median()


def find_surges(forecast: pd.DataFrame, daily: pd.DataFrame, cal: pd.DataFrame,
                factor: float = SURGE_FACTOR, cfg: dict | None = None) -> list[dict]:
    cfg = cfg or load_workload()
    typical = typical_levels(daily, cal)
    wide = (forecast[forecast["category"] != "total"]
            .pivot_table(index="date", columns="category", values="forecast")
            .reindex(columns=CATEGORY_KEYS, fill_value=0.0).fillna(0.0))
    wide["total"] = wide[CATEGORY_KEYS].sum(axis=1)
    surges = []
    for d, row in wide.iterrows():
        if d.dayofweek >= 5 or d not in cal.index or cal.loc[d, "is_public_holiday"]:
            continue
        normal = typical.loc[d.dayofweek] if d.dayofweek in typical.index else None
        if normal is None:
            continue
        base_total = max(float(normal["total"]), TYPICAL_FLOOR)
        expected = float(row["total"])
        if expected < base_total * factor or expected - base_total < MIN_EXTRA_TICKETS:
            continue

        increases = {c: float(row[c]) - float(normal[c]) for c in CATEGORY_KEYS}
        top_cat = max(increases, key=increases.get)
        extra_hours = sum(max(0.0, inc) * cfg["handling_minutes"][c] / 60 for c, inc in increases.items())
        reasons = describe_day(cal.loc[d].to_dict())
        surges.append({
            "date": d.date().isoformat(),
            "expected_tickets": round(expected, 1),
            "typical_tickets": round(base_total, 1),
            "ratio": round(expected / base_total, 2),
            "main_category": top_cat,
            "main_category_name": CATEGORIES[top_cat].display_name,
            "routes_to": CATEGORIES[top_cat].routed_role,
            "drivers": reasons or ["no calendar event (check for other causes)"],
            "extra_staff_hours": round(extra_hours, 1),
        })
    return surges
