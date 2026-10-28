"""Week 8: compute and store today's forecast and the pinned demo dates, plus a forecast run.

Runs in GitHub Actions every night (connected straight to Supabase), so the Render API never
has to do this heavy work on its 0.1 CPU. Same as POST /jobs/refresh-forecast.

Needs DATABASE_URL (the database to update) and JOBS_TOKEN (the same value as on Render:
stored forecasts are signed with it, and the API only trusts what it can verify).

Usage:
    python scripts/refresh_forecasts.py
    python scripts/refresh_forecasts.py --dates 2025-12-15 2026-01-12   # only these dates
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.forecasting import service as fc  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dates", nargs="*", help="Forecast dates (YYYY-MM-DD). Default: today + pinned dates")
    args = parser.parse_args()
    if not get_settings().jobs_token:
        sys.exit("JOBS_TOKEN is empty: stored forecasts must be signed with the same token as the API.")

    start = time.perf_counter()
    init_db()
    with SessionLocal() as db:
        done = fc.refresh_stored(db, args.dates or None)
        for d in done:
            print(f"{d['as_of']}: " + (f"stored ({d['seconds']} s)" if d["stored"] else f"skipped: {d.get('reason')}"))
        if not args.dates:
            run = fc.save_run(db, fc.get_bundle(db, None), 60)
            print(f"forecast run #{run.id} saved for {run.as_of}")
    if not any(d["stored"] for d in done):
        sys.exit("Nothing was stored.")
    print(f"done in {time.perf_counter() - start:.1f} s")


if __name__ == "__main__":
    main()
