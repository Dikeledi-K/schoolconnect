"""Fill the database with SYNTHETIC ticket history, from a fixed start date up to yesterday.

The start date is FIXED (default 25 October 2024) rather than "24 months ago", so the history is
the same whichever day you run this: each day's tickets depend only on the days before it.
That keeps the documented results reproducible (e.g. the January 2026 backtest in
docs/forecast_evaluation.md). Running it on a later day only ADDS the newer days.

Usage:
    python scripts/generate_history.py --reset              # drops ALL tables and rebuilds
    python scripts/generate_history.py                      # adds history if the table is empty
    python scripts/generate_history.py --start 2025-01-01 --seed 7
    python scripts/generate_history.py --months 12          # "the last 12 months" (not reproducible)
"""

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, insert, select  # noqa: E402

from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.models import Ticket  # noqa: E402
from app.synthetic import TZ, generate_tickets  # noqa: E402


DEFAULT_START = date(2024, 10, 25)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables first")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START,
                        help=f"first day of history (default {DEFAULT_START}, keeps results reproducible)")
    parser.add_argument("--months", type=int, default=None,
                        help="instead of --start: this many months back from yesterday (results change daily)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(engine)
    init_db()

    with SessionLocal() as db:
        existing = db.scalar(select(func.count(Ticket.id)))
        if existing and not args.reset:
            print(f"Database already has {existing} tickets. Use --reset to rebuild.")
            return

        now = datetime.now(TZ)
        end = (now - timedelta(days=1)).date()            # history ends yesterday
        start = end - timedelta(days=int(args.months * 30.44)) if args.months else args.start
        print(f"Generating synthetic tickets from {start} to {end} (seed {args.seed}) ...")
        rows = generate_tickets(start, end, seed=args.seed, now=now)

        for i in range(0, len(rows), 2000):
            db.execute(insert(Ticket), rows[i:i + 2000])
        db.commit()
        print(f"Inserted {len(rows)} synthetic tickets.")


if __name__ == "__main__":
    main()
