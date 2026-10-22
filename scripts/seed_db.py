"""Load data/sample_messages.csv into the database as demo tickets.

Ticket dates are spread over the last 60 days (weekdays and office hours are
more likely, like a real school office). Older tickets are more likely to be
resolved already, so the staff inbox looks realistic.

Usage:
    python scripts/seed_db.py            # add the 150 demo tickets
    python scripts/seed_db.py --reset    # delete ALL tickets first
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import crud  # noqa: E402
from app.classifier import classify_message  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Ticket  # noqa: E402
from app.schemas import TicketCreate  # noqa: E402
from scripts.evaluate_classifier import load_rows  # noqa: E402

DAYS_BACK = 60
SEED = 42  # fixed seed: the same demo data every time


def random_timestamp(rng: random.Random, now: datetime) -> datetime:
    """A time in the last DAYS_BACK days; weekdays 3x as likely, 07:00-18:59."""
    while True:
        day = now - timedelta(days=rng.randint(0, DAYS_BACK - 1))
        weight = 3 if day.weekday() < 5 else 1
        if rng.random() < weight / 3:
            break
    moment = day.replace(hour=rng.randint(7, 18), minute=rng.randint(0, 59), second=0, microsecond=0)
    return min(moment, now)  # never in the future


def seed(db: Session, rows: list[dict], now: datetime | None = None, rng_seed: int = SEED) -> int:
    """Insert one ticket per row. Returns the number created."""
    rng = random.Random(rng_seed)
    now = now or datetime.now(timezone.utc)

    # Sort by date first so references (SC-YYYYMMDD-0001...) count up in time order.
    planned = sorted(((random_timestamp(rng, now), row) for row in rows), key=lambda p: p[0])

    for created_at, row in planned:
        data = TicketCreate(
            message=row["message"],
            learner_grade=row.get("learner_grade") or None,
            channel=rng.choice(["web", "web", "whatsapp", "email"]),
        )
        ticket = crud.create_ticket(db, data, classify_message(row["message"]), created_at=created_at)

        # Older tickets are more likely to be finished; a few old ones are
        # left "new" on purpose (useful for SLA checks in later weeks).
        age_days = (now - created_at).days
        roll = rng.random()
        resolve_chance = 0.8 if age_days > 7 else 0.3
        if roll < resolve_chance:
            ticket.status = "resolved"
            ticket.resolved_at = min(created_at + timedelta(hours=rng.randint(2, 96)), now)
            ticket.updated_at = ticket.resolved_at
        elif roll < 0.9:
            ticket.status = "in_progress"
            ticket.updated_at = min(created_at + timedelta(hours=rng.randint(1, 24)), now)
    db.commit()
    return len(planned)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete all tickets first")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db:
        if args.reset:
            db.execute(delete(Ticket))
            db.commit()
            print("Deleted existing tickets.")
        count = seed(db, load_rows())
    print(f"Seeded {count} tickets over the last {DAYS_BACK} days.")


if __name__ == "__main__":
    main()
