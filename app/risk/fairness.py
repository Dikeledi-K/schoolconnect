"""Bias and fairness checks: does SchoolConnect treat every group of parents equally well?

Three checks, each broken down by LANGUAGE and by GRADE BAND:
  1. Classifier accuracy on the labelled sample data (data/sample_messages.csv).
     A group is flagged if its accuracy is more than 10 percentage points below overall.
  2. Service: median hours from message to resolution, from real tickets.
     A group is flagged if it waits more than 1.5x the overall median.
  3. Human overrides: how often staff had to correct the AI's classification.
     A group is flagged if its correction rate is more than 10 points above overall.

Small groups are reported but never flagged (too few cases to judge fairly).
"""

from __future__ import annotations

import csv
from pathlib import Path
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AIAuditLog, Ticket
from app.taxonomy import LANGUAGES

SAMPLE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "sample_messages.csv"

ACCURACY_GAP = 0.10        # flag if accuracy is 10+ points below overall
WAIT_RATIO = 1.5           # flag if median wait is 1.5x overall or more
OVERRIDE_GAP = 0.10        # flag if correction rate is 10+ points above overall
MIN_SAMPLE_GROUP = 5       # labelled messages needed before we judge a group
MIN_TICKET_GROUP = 20      # resolved tickets needed before we judge a group
MIN_OVERRIDE_GROUP = 10    # classified tickets needed before we judge a group


def grade_band(grade: str | None) -> str:
    """Group grades into the CAPS school phases."""
    if not grade:
        return "Not given"
    if grade in ("R", "1", "2", "3"):
        return "Foundation (R-3)"
    if grade in ("4", "5", "6"):
        return "Intermediate (4-6)"
    if grade in ("7", "8", "9"):
        return "Senior (7-9)"
    return "FET (10-12)"


def _language_name(code: str) -> str:
    return LANGUAGES.get(code, code)


def classifier_fairness(path: Path = SAMPLE_FILE) -> dict:
    """Accuracy of the RULES classifier per language and grade band on the labelled sample."""
    from app.classifier import classify_message

    rules_only = Settings(llm_provider="rules", anthropic_api_key="", gemini_api_key="")
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    results = []
    for row in rows:
        predicted = classify_message(row["message"], settings=rules_only)
        results.append({"language": row["expected_language"], "band": grade_band(row.get("learner_grade") or None),
                        "correct": predicted.category == row["expected_category"]})
    overall = sum(r["correct"] for r in results) / len(results) if results else 0.0

    def groups(key, label_fn):
        out = []
        for value in sorted({r[key] for r in results}):
            subset = [r for r in results if r[key] == value]
            acc = sum(r["correct"] for r in subset) / len(subset)
            flagged = len(subset) >= MIN_SAMPLE_GROUP and acc < overall - ACCURACY_GAP
            out.append({"group": label_fn(value), "n": len(subset), "accuracy": round(acc, 3),
                        "flagged": flagged, "too_small": len(subset) < MIN_SAMPLE_GROUP})
        return out

    return {"overall_accuracy": round(overall, 3), "messages": len(results),
            "by_language": groups("language", _language_name), "by_grade": groups("band", str)}


def _hours(ticket: Ticket) -> float:
    return (ticket.resolved_at - ticket.created_at).total_seconds() / 3600


def service_fairness(db: Session) -> dict:
    """Median hours to resolution per language and grade band (resolved tickets only)."""
    tickets = list(db.scalars(select(Ticket).where(Ticket.status == "resolved",
                                                   Ticket.resolved_at.is_not(None))))
    waits = [(t, _hours(t)) for t in tickets]
    overall = median(h for _, h in waits) if waits else 0.0

    def groups(key_fn, label_fn):
        out = []
        for value in sorted({key_fn(t) for t, _ in waits}):
            hours = [h for t, h in waits if key_fn(t) == value]
            med = median(hours)
            flagged = len(hours) >= MIN_TICKET_GROUP and overall > 0 and med >= overall * WAIT_RATIO
            out.append({"group": label_fn(value), "n": len(hours), "median_hours": round(med, 1),
                        "flagged": flagged, "too_small": len(hours) < MIN_TICKET_GROUP})
        return out

    return {"overall_median_hours": round(overall, 1), "resolved_tickets": len(waits),
            "by_language": groups(lambda t: t.language, _language_name),
            "by_grade": groups(lambda t: grade_band(t.learner_grade), str)}


def override_fairness(db: Session) -> dict:
    """How often staff corrected the AI's classification, per language and grade band."""
    classified = set(db.scalars(select(AIAuditLog.ticket_id).where(AIAuditLog.feature == "classification")))
    corrected = set(db.scalars(select(AIAuditLog.ticket_id).where(AIAuditLog.feature == "human_override")))
    tickets = list(db.scalars(select(Ticket).where(Ticket.id.in_(classified)))) if classified else []
    overall = (sum(t.id in corrected for t in tickets) / len(tickets)) if tickets else 0.0

    def groups(key_fn, label_fn):
        out = []
        for value in sorted({key_fn(t) for t in tickets}):
            subset = [t for t in tickets if key_fn(t) == value]
            rate = sum(t.id in corrected for t in subset) / len(subset)
            flagged = len(subset) >= MIN_OVERRIDE_GROUP and rate > overall + OVERRIDE_GAP
            out.append({"group": label_fn(value), "n": len(subset), "override_rate": round(rate, 3),
                        "flagged": flagged, "too_small": len(subset) < MIN_OVERRIDE_GROUP})
        return out

    return {"overall_override_rate": round(overall, 3), "classified_tickets": len(tickets),
            "by_language": groups(lambda t: t.language, _language_name),
            "by_grade": groups(lambda t: grade_band(t.learner_grade), str)}


def fairness_report(db: Session) -> dict:
    report = {"classifier": classifier_fairness(), "service": service_fairness(db),
              "overrides": override_fairness(db)}
    flags = []
    labels = {"classifier": ("accuracy", "classifier accuracy"),
              "service": ("median_hours", "median hours to resolution"),
              "overrides": ("override_rate", "staff correction rate")}
    for section, (metric, description) in labels.items():
        for dimension in ("by_language", "by_grade"):
            for g in report[section][dimension]:
                if g["flagged"]:
                    flags.append(f"{g['group']}: {description} {g[metric]} (n={g['n']})")
    report["flags"] = flags
    report["thresholds"] = {"accuracy_gap": ACCURACY_GAP, "wait_ratio": WAIT_RATIO, "override_gap": OVERRIDE_GAP}
    return report
