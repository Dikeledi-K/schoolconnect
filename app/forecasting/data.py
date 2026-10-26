"""Turns individual tickets into a daily count table, one column per category."""

from datetime import datetime, timezone

import pandas as pd

from app.taxonomy import CATEGORIES

CATEGORY_KEYS = list(CATEGORIES)

# The school's local timezone. Tickets are stored in UTC; days are counted in local time.
SCHOOL_TIMEZONE = "Africa/Johannesburg"


def daily_counts(rows, start=None, end=None) -> pd.DataFrame:
    """Daily ticket counts per category, zero-filled, plus a "total" column.

    rows: iterable of (created_at, category). Naive datetimes are treated as UTC
    (that is how the database stores them). Days are counted in school local time.
    """
    rows = list(rows)
    if rows:
        df = pd.DataFrame(rows, columns=["created_at", "category"])
        ts = pd.to_datetime(
            [t if t.tzinfo else t.replace(tzinfo=timezone.utc) for t in df["created_at"]], utc=True
        )
        df["date"] = ts.tz_convert(SCHOOL_TIMEZONE).tz_localize(None).normalize()
        table = df.pivot_table(index="date", columns="category", aggfunc="size", fill_value=0)
    else:
        table = pd.DataFrame()

    if start is None:
        start = table.index.min() if len(table) else datetime.now().date()
    if end is None:
        end = table.index.max() if len(table) else start
    days = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq="D")

    table = table.reindex(index=days, columns=CATEGORY_KEYS, fill_value=0).fillna(0).astype(int)
    table.index.name = "date"
    table["total"] = table[CATEGORY_KEYS].sum(axis=1)
    return table
