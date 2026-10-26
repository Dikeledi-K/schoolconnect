"""Turns config/school_calendar.yaml into one row of flags per day.

These flags are what the forecasting models "know" about each day, e.g.
"this is the first week of term" or "the admissions window is open".
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

# config/ lives at the repo root, next to app/.
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"

CALENDAR_FILE = CONFIG_DIR / "school_calendar.yaml"

FLAG_COLUMNS = [
    "is_weekend", "is_public_holiday", "is_school_day", "is_holiday_break", "pre_term_week",
    "term_week_1_2", "term_week_3_4", "school_year_start", "admissions_window", "placement_offers", "exam_period",
    "report_window", "month_start",
]


@lru_cache
def load_calendar(path: str = str(CALENDAR_FILE)) -> dict:
    with open(Path(path)) as f:
        return yaml.safe_load(f)


def _in_ranges(days: pd.DatetimeIndex, ranges) -> pd.Series:
    mask = pd.Series(False, index=days)
    for start, end in ranges:
        mask |= (days >= pd.Timestamp(start)) & (days <= pd.Timestamp(end))
    return mask


def calendar_features(start, end, path: str = str(CALENDAR_FILE)) -> pd.DataFrame:
    """Daily calendar flags (0/1 integers) between start and end inclusive."""
    days = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq="D")
    cal = load_calendar(path)["years"]

    terms, holidays, adm, place, exams, reports = [], [], [], [], [], []
    for year in cal.values():
        terms += year.get("terms", [])
        holidays += year.get("public_holidays", [])
        adm += year.get("admissions_windows", [])
        place += year.get("placement_offers", [])
        exams += year.get("exam_periods", [])
        reports += year.get("report_days", [])

    df = pd.DataFrame(index=days)
    df.index.name = "date"
    df["day_of_week"] = days.dayofweek
    df["is_weekend"] = days.dayofweek >= 5
    df["is_public_holiday"] = days.isin(pd.to_datetime(holidays))
    in_term = _in_ranges(days, terms)
    df["is_school_day"] = in_term & ~df["is_weekend"] & ~df["is_public_holiday"]
    df["is_holiday_break"] = ~in_term

    # Weeks since the most recent term start (0 = first week of term).
    term_starts = sorted(pd.Timestamp(s) for s, _ in terms)
    df["days_since_term_start"] = -1
    for d in days:
        past = [s for s in term_starts if s <= d]
        if past and in_term[d]:
            df.at[d, "days_since_term_start"] = (d - past[-1]).days
    df["term_week_1_2"] = in_term & (df["days_since_term_start"].between(0, 13))
    df["term_week_3_4"] = in_term & (df["days_since_term_start"].between(14, 27))

    # The 7 days before any term start: offices reopen and parents start calling.
    pre = pd.Series(False, index=days)
    for s in term_starts:
        pre |= (days >= s - pd.Timedelta(days=7)) & (days < s)
    df["pre_term_week"] = pre

    # Start of the school year: the week before Term 1 plus its first 4 weeks.
    # This is the biggest rush of the year (late admissions, fees, transport, stationery).
    first_terms = []
    for year in cal.values():
        if year.get("terms"):
            first_terms.append(pd.Timestamp(year["terms"][0][0]))
    ys = pd.Series(False, index=days)
    for s in first_terms:
        ys |= (days >= s - pd.Timedelta(days=7)) & (days < s + pd.Timedelta(days=28))
    df["school_year_start"] = ys

    df["admissions_window"] = _in_ranges(days, adm)
    df["placement_offers"] = _in_ranges(days, place)
    df["exam_period"] = _in_ranges(days, exams)
    # Report window: report day plus the following 10 calendar days (parents react to reports).
    df["report_window"] = _in_ranges(
        days, [(r, (pd.Timestamp(r) + pd.Timedelta(days=10)).date().isoformat()) for r in reports]
    )
    df["month_start"] = days.day <= 7

    for col in FLAG_COLUMNS:
        df[col] = df[col].astype(int)
    return df


def describe_day(row) -> list[str]:
    """Human-readable calendar reasons for a day, used to explain surges."""
    reasons = []
    if row.get("school_year_start"):
        reasons.append("the start of the school year")
    if row.get("pre_term_week"):
        reasons.append("the week before term starts")
    if row.get("term_week_1_2"):
        reasons.append("the first two weeks of term")
    if row.get("admissions_window"):
        reasons.append("the admissions application window")
    if row.get("placement_offers"):
        reasons.append("admissions placement offers and appeals")
    if row.get("exam_period"):
        reasons.append("exam period")
    if row.get("report_window"):
        reasons.append("reports being issued")
    if row.get("month_start") and not row.get("is_weekend"):
        reasons.append("month-start fee payments")
    return reasons
