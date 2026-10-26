"""Turns forecast tickets into staff hours and capacity utilisation per role."""

from functools import lru_cache

import pandas as pd
import yaml

from app.forecasting.calendar import CONFIG_DIR
from app.taxonomy import CATEGORIES, STAFF_ROLES

WORKLOAD_FILE = CONFIG_DIR / "workload.yaml"


@lru_cache
def load_workload(path: str = str(WORKLOAD_FILE)) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def status_for(utilisation: float, cfg: dict) -> str:
    if utilisation > cfg["overload_threshold"]:
        return "overloaded"
    if utilisation >= cfg["busy_threshold"]:
        return "busy"
    return "ok"


def is_office_day(row) -> bool:
    return not row["is_weekend"] and not row["is_public_holiday"]


def daily_workload(forecast: pd.DataFrame, cal: pd.DataFrame, staff_override: dict | None = None,
                   cfg: dict | None = None, buffer: float = 0.0) -> pd.DataFrame:
    """One row per (date, role): tickets, hours_needed, capacity_hours, utilisation, status.

    buffer: planning margin for a "busy week" scenario. We use the forecast's own average
    backtest error (e.g. 0.22 = forecasts were 22% off on average), so hours_upper means
    "what if demand is as much higher than forecast as our typical error?"

    Tickets that arrive on weekends or public holidays are added to the next office day,
    because that is when staff will actually deal with them.
    """
    cfg = cfg or load_workload()
    staff = {**cfg["staff"], **(staff_override or {})}
    fc = forecast[forecast["category"] != "total"].copy()
    fc["role"] = fc["category"].map(lambda c: CATEGORIES[c].routed_role)
    minutes = fc["category"].map(cfg["handling_minutes"])
    fc["hours"] = fc["forecast"] * minutes / 60
    fc["hours_upper"] = fc["hours"] * (1 + buffer)   # "busy week" scenario
    per_day = (fc.groupby(["date", "role"])[["forecast", "hours", "hours_upper"]].sum()
               .unstack("role", fill_value=0))

    dates = sorted(fc["date"].unique())
    rows = []
    carry_hours = {r: 0.0 for r in STAFF_ROLES}
    carry_upper = {r: 0.0 for r in STAFF_ROLES}
    carry_tickets = {r: 0.0 for r in STAFF_ROLES}

    def get(col, role, d):
        return per_day[col][role][d] if role in per_day[col].columns else 0.0

    for d in dates:
        flags = cal.loc[d]
        office = is_office_day(flags)
        factor = 1.0
        if flags["is_holiday_break"] and not flags["pre_term_week"]:
            factor = cfg["holiday_capacity_factor"]
        for role in STAFF_ROLES:
            hours = get("hours", role, d) + carry_hours[role]
            upper = get("hours_upper", role, d) + carry_upper[role]
            tickets = get("forecast", role, d) + carry_tickets[role]
            if not office:
                carry_hours[role], carry_upper[role], carry_tickets[role] = hours, upper, tickets
                continue
            carry_hours[role] = carry_upper[role] = carry_tickets[role] = 0.0
            capacity = staff.get(role, 0) * cfg["hours_per_day"][role] * factor
            util = hours / capacity if capacity > 0 else (float("inf") if hours > 0 else 0.0)
            rows.append({"date": d, "role": role, "role_name": STAFF_ROLES[role],
                         "tickets": tickets, "hours_needed": hours, "hours_upper": upper,
                         "capacity_hours": capacity,
                         "staff": staff.get(role, 0), "utilisation": util,
                         "status": status_for(util, cfg)})
    return pd.DataFrame(rows)


def weekly_workload(daily: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """Same as daily_workload but summed per week (weeks start on Monday)."""
    cfg = cfg or load_workload()
    if daily.empty:
        return daily
    df = daily.copy()
    df["week_start"] = df["date"] - pd.to_timedelta(df["date"].dt.dayofweek, unit="D")
    cols = ["tickets", "hours_needed", "hours_upper", "capacity_hours"]
    w = df.groupby(["week_start", "role", "role_name"])[cols].sum().reset_index()
    cap = w["capacity_hours"].where(w["capacity_hours"] > 0)
    w["utilisation"] = (w["hours_needed"] / cap).fillna(0.0)
    w["utilisation_upper"] = (w["hours_upper"] / cap).fillna(0.0)
    w["status"] = w["utilisation"].map(lambda u: status_for(u, cfg))
    # Expected to cope, but a busy-but-plausible week would overload this role.
    w["overload_risk"] = (w["status"] != "overloaded") & (w["utilisation_upper"] > cfg["overload_threshold"])
    return w


def category_mix(forecast: pd.DataFrame, role: str, start, end) -> list[tuple[str, float]]:
    """Which categories make up a role's tickets in a period, largest first."""
    cats = [c for c, info in CATEGORIES.items() if info.routed_role == role]
    fc = forecast[(forecast["category"].isin(cats)) & (forecast["date"] >= start) & (forecast["date"] <= end)]
    mix = fc.groupby("category")["forecast"].sum().sort_values(ascending=False)
    return list(mix.items())
