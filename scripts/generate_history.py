"""Fill the database with ~24 months of SYNTHETIC ticket history.

Usage:
    python scripts/generate_history.py            # adds history if the table is empty
    python scripts/generate_history.py --reset    # drops all tables and rebuilds
    python scripts/generate_history.py --months 24 --seed 42
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, insert, select  # noqa: E402

from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.models import Ticket  # noqa: E402
from app.synthetic import TZ, generate_tickets  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables first")
    parser.add_argument("--months", type=int, default=24)
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
        start = end - timedelta(days=int(args.months * 30.44))
        print(f"Generating synthetic tickets from {start} to {end} (seed {args.seed}) ...")
        rows = generate_tickets(start, end, seed=args.seed, now=now)

        for i in range(0, len(rows), 2000):
            db.execute(insert(Ticket), rows[i:i + 2000])
        db.commit()
        print(f"Inserted {len(rows)} synthetic tickets.")


if __name__ == "__main__":
    main()
