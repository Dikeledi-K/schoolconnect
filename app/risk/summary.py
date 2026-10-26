"""Collects everything the principal needs to judge AI risk over a period.

Sections: AI decisions, guardrails fired, personal data masked, human overrides, reply drafts,
safety incidents, fairness, prompt-injection results, retention status and the risk register.
All numbers are counts; no personal data appears in the summary.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.models import Response, Ticket
from app.privacy.retention import find_candidates
from app.risk import fairness, injection

RISK_REGISTER_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "risk_register.yaml"


@lru_cache
def load_risk_register(path: str = str(RISK_REGISTER_FILE)) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["risks"]


def _aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes (stored as UTC); make them comparable."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def build_summary(db: Session, days: int = 30, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    rows = audit.since(db, start)

    by_feature = Counter(r.feature for r in rows)
    classifications = [r for r in rows if r.feature == "classification"]
    drafts = [r for r in rows if r.feature == "response_draft"]
    guardrails = Counter(g for r in rows if r.feature in ("classification", "human_override") for g in r.guardrails)
    pii = Counter()
    for r in rows:
        if r.feature != "retention":
            pii.update(r.pii_found)
    overrides = [r for r in rows if r.feature == "human_override"]

    tickets = list(db.scalars(select(Ticket).where(Ticket.created_at >= start)))
    open_critical_old = [t for t in tickets if t.urgency == "critical" and t.status == "new"
                         and _aware(t.created_at) < now - timedelta(hours=1)]
    responses = list(db.scalars(select(Response).where(Response.created_at >= start)))
    approved = [r for r in responses if r.status == "approved"]

    inj = injection.summary()
    return {
        "period": {"days": days, "start": start.date().isoformat(), "end": now.date().isoformat()},
        "ai_decisions": {
            "by_feature": dict(by_feature),
            "classifications": len(classifications),
            "classified_by_ai": sum(r.llm_used for r in classifications),
            "ai_fallbacks_to_rules": sum(1 for r in classifications if r.fallback_reason),
            "reply_drafts": len(drafts),
            "reply_drafts_by_ai": sum(r.llm_used for r in drafts),
            "ai_replies_rejected": sum(1 for r in drafts if (r.fallback_reason or "").startswith("AI reply rejected")),
        },
        "guardrails_fired": dict(guardrails),
        "pii_masked": dict(pii),
        "human_overrides": {
            "count": len(overrides),
            "recent": [{"when": r.created_at.isoformat(timespec="minutes"), "ticket_id": r.ticket_id,
                        "by": r.actor, "before": r.output.get("before"), "after": r.output.get("after"),
                        "reason": r.output.get("reason"), "guardrails": r.guardrails}
                       for r in overrides[-10:]],
        },
        "replies": {
            "drafted": len(responses),
            "approved": len(approved),
            "edited_before_approval": sum(r.edited for r in approved),
            "acknowledgement_only": sum(r.acknowledgement_only for r in responses),
        },
        "incidents": {
            "tickets": len(tickets),
            "critical": sum(t.urgency == "critical" for t in tickets),
            "safety_flagged": sum(t.safety_flag for t in tickets),
            "critical_still_new_after_1h": len(open_critical_old),
        },
        "fairness": fairness.fairness_report(db),
        "prompt_injection": {"checks": inj["checks"], "passed": inj["passed"], "failed": inj["failed"],
                             "results": inj["results"]},
        "retention": {"tickets_due_for_anonymising": len(find_candidates(db, now))},
        "total_audit_rows": db.scalar(select(func.count()).select_from(audit.AIAuditLog)) or 0,
        "risk_register": load_risk_register(),
    }
