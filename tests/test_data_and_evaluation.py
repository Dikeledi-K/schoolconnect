"""The sample dataset, the seed script and the Week 1 accuracy targets."""

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Ticket
from app.taxonomy import CATEGORIES, LANGUAGES, URGENCY_LEVELS
from scripts.evaluate_classifier import compute_metrics, load_rows, run_classifier
from scripts.seed_db import DAYS_BACK, seed
from app.config import Settings

ROWS = load_rows()


def test_dataset_shape():
    assert len(ROWS) == 150
    for row in ROWS:
        assert row["message"].strip()
        assert row["expected_category"] in CATEGORIES
        assert row["expected_urgency"] in URGENCY_LEVELS
        assert row["expected_language"] in LANGUAGES
        assert row["split"] in ("dev", "holdout")


def test_dataset_mix():
    non_english = sum(r["expected_language"] != "en" for r in ROWS)
    assert 0.25 <= non_english / len(ROWS) <= 0.40
    welfare = sum(r["expected_category"] == "learner_welfare" for r in ROWS)
    assert 10 <= welfare <= 14
    assert set(Counter(r["expected_category"] for r in ROWS)) == set(CATEGORIES)


def test_classifier_meets_week1_targets():
    """Rules accuracy >= 75% and ZERO missed critical cases."""
    metrics = compute_metrics(run_classifier(ROWS, Settings(llm_provider="rules")))
    assert metrics["accuracy"] >= 0.75
    assert metrics["missed_critical"] == []


def test_seed_spreads_dates_over_60_days(db_session):
    now = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    assert seed(db_session, ROWS[:40], now=now) == 40
    tickets = list(db_session.scalars(select(Ticket)))
    assert len(tickets) == 40
    # SQLite returns naive datetimes; treat them as UTC.
    dates = [t.created_at.replace(tzinfo=timezone.utc) for t in tickets]
    assert min(dates) >= now - timedelta(days=DAYS_BACK)
    assert max(dates) <= now
    assert len({d.date() for d in dates}) > 15  # genuinely spread out
    assert {t.status for t in tickets} <= {"new", "in_progress", "resolved"}
    assert len({t.reference for t in tickets}) == 40
