"""Week 6: fairness checks must flag a planted bias and ignore groups that are too small."""

from datetime import datetime, timedelta, timezone

from app import audit
from app.models import Ticket
from app.risk.fairness import fairness_report, grade_band, service_fairness

NOW = datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc)


def _ticket(i, language, hours, grade="4"):
    return Ticket(reference=f"SC-20260302-{i:04d}", message="synthetic", learner_grade=grade, channel="web",
                  category="academic", urgency="low", language=language, routed_role="class_teacher",
                  confidence=0.9, method="rules", needs_human=False, safety_flag=False, reason="",
                  status="resolved", created_at=NOW, updated_at=NOW, resolved_at=NOW + timedelta(hours=hours))


def test_grade_bands():
    assert grade_band("R") == "Foundation (R-3)" and grade_band("6") == "Intermediate (4-6)"
    assert grade_band("9") == "Senior (7-9)" and grade_band("12") == "FET (10-12)"
    assert grade_band(None) == "Not given"


def test_slow_service_for_one_language_is_flagged(db_session):
    # 60 English tickets resolved in 10 h; 25 isiZulu tickets take 30 h (planted bias);
    # 3 Sesotho tickets take 50 h, but 3 is too few to judge.
    rows = ([_ticket(i, "en", 10) for i in range(60)] + [_ticket(100 + i, "zu", 30) for i in range(25)]
            + [_ticket(200 + i, "st", 50) for i in range(3)])
    db_session.add_all(rows)
    db_session.commit()
    result = service_fairness(db_session)
    groups = {g["group"]: g for g in result["by_language"]}
    assert groups["isiZulu"]["flagged"]
    assert not groups["English"]["flagged"]
    assert groups["Sesotho"]["too_small"] and not groups["Sesotho"]["flagged"]
    assert any("isiZulu" in f for f in fairness_report(db_session)["flags"])


def test_high_correction_rate_for_one_language_is_flagged(db_session):
    rows = [_ticket(i, "en", 5) for i in range(40)] + [_ticket(100 + i, "af", 5) for i in range(12)]
    db_session.add_all(rows)
    db_session.commit()
    for t in rows:
        audit.record(db_session, "classification", "rules", ticket_id=t.id, commit=False)
    for t in rows[40:46]:   # half of the Afrikaans tickets had to be corrected
        audit.record(db_session, "human_override", "staff", ticket_id=t.id, human_override=True, commit=False)
    db_session.commit()
    report = fairness_report(db_session)
    groups = {g["group"]: g for g in report["overrides"]["by_language"]}
    assert groups["Afrikaans"]["flagged"] and groups["Afrikaans"]["override_rate"] == 0.5
    assert not groups["English"]["flagged"]
