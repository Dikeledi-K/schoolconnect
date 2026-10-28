"""Weeks 3-4: make the weekly business reports (whole school + every department) from the command line.

Same as the scheduled job POST /jobs/weekly-reports. Reports that already exist are kept
unless you pass --force. Staff who may read a report get a "your report is ready" message in
the outbox (dry run unless NOTIFY_MODE=smtp).

Usage:
    python scripts/make_weekly_reports.py                    # last completed week
    python scripts/make_weekly_reports.py --week 2026-01-12  # a specific week (a Monday)
    python scripts/make_weekly_reports.py --weeks 4          # the last 4 completed weeks
    python scripts/make_weekly_reports.py --force            # remake reports that already exist
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.analytics.metrics import last_full_week  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.reports.weekly import ReportError, run_weekly_job  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--week", type=date.fromisoformat, help="Monday of the week (YYYY-MM-DD)")
    parser.add_argument("--weeks", type=int, default=1, help="How many recent completed weeks to make")
    parser.add_argument("--force", action="store_true", help="Remake reports that already exist")
    parser.add_argument("--no-outlook", action="store_true", help="Skip next week's forecast (faster)")
    args = parser.parse_args()

    init_db()
    mondays = [args.week] if args.week else [last_full_week()[0] - timedelta(weeks=i) for i in range(args.weeks)]
    with SessionLocal() as db:
        for monday in sorted(mondays):
            try:
                result = run_weekly_job(db, week_start=monday, force=args.force,
                                        include_outlook=not args.no_outlook)
            except ReportError as exc:
                sys.exit(f"{monday}: {exc}")
            print(f"Week of {monday}: made {len(result['created'])} report(s)"
                  + (f", kept {len(result['skipped_existing'])} existing" if result["skipped_existing"] else ""))
    print("Open SchoolConnect > Weekly reports to read or download them.")


if __name__ == "__main__":
    main()
