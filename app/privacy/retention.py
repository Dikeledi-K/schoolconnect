"""POPIA retention: personal data is kept only as long as it is needed.

Rule (see docs/POPIA.md): RESOLVED tickets whose resolution is older than RETENTION_DAYS
(default 365) are anonymised: the parent's name and contact are removed, and personal data
in the message is masked. Open tickets are never touched. The ticket's category and dates
stay, so statistics and forecasts keep working.

Dry run is the default: it reports what WOULD change and changes nothing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, crud
from app.config import get_settings
from app.models import Ticket
from app.privacy.pii import mask_pii


def _needs_anonymising(ticket: Ticket) -> bool:
    if ticket.parent_name or ticket.parent_contact:
        return True
    return mask_pii(ticket.message).found


def find_candidates(db: Session, now: datetime | None = None, days: int | None = None) -> list[Ticket]:
    now = now or datetime.now(timezone.utc)
    days = get_settings().retention_days if days is None else days
    cutoff = now - timedelta(days=days)
    query = select(Ticket).where(Ticket.status == "resolved", Ticket.resolved_at.is_not(None),
                                 Ticket.resolved_at < cutoff)
    return [t for t in db.scalars(query) if _needs_anonymising(t)]


def run_retention(db: Session, now: datetime | None = None, days: int | None = None,
                  dry_run: bool = True) -> dict:
    now = now or datetime.now(timezone.utc)
    days = get_settings().retention_days if days is None else days
    candidates = find_candidates(db, now, days)
    removed_totals: dict[str, int] = {}
    if not dry_run:
        for ticket in candidates:
            for key, n in crud.anonymise_ticket(db, ticket, commit=False).items():
                removed_totals[key] = removed_totals.get(key, 0) + n
        audit.record(db, "retention", "job", output={"days": days, "anonymised": len(candidates)},
                     pii_found=removed_totals, commit=False)
        db.commit()
    return {
        "dry_run": dry_run,
        "retention_days": days,
        "cutoff": (now - timedelta(days=days)).date().isoformat(),
        "tickets_to_anonymise" if dry_run else "tickets_anonymised": len(candidates),
        "references": [t.reference for t in candidates[:50]],
        "removed": removed_totals,
    }
