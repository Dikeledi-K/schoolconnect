"""Week 6: prompt-injection suite (cases in data/prompt_injection_cases.json)."""

from unittest.mock import patch

import pytest

from app.classifier import classify_message
from app.risk.injection import load_cases, run_suite, summary

RESULTS = run_suite()


@pytest.mark.parametrize("result", RESULTS, ids=lambda r: f"{r['id']}-{r['layer']}")
def test_every_injection_check_passes(result):
    assert result["passed"], result["detail"]


def test_suite_covers_all_layers():
    layers = {r["layer"] for r in RESULTS}
    assert layers == {"rules", "hostile_ai", "prompt_wrap", "grounding"}
    cases = load_cases()
    assert len(RESULTS) == 3 * len(cases["classification"]) + len(cases["replies"])


def test_suite_detects_a_broken_guardrail():
    """If the guardrails stopped working, the suite must notice (it is not a rubber stamp)."""
    with patch("app.risk.injection.apply_guardrails", side_effect=lambda message, result: result):
        broken = summary(run_suite())
    assert broken["failed"], "suite should fail when guardrails are disabled"


def test_end_to_end_with_obedient_ai():
    """Full classify_message() path with an AI that obeyed the attack."""
    obeyed = {"category": "other", "urgency": "low", "language": "en", "confidence": 0.99,
              "reason": "as instructed"}
    with patch("app.classifier.service.classify_with_llm", return_value=obeyed):
        for case in load_cases()["classification"]:
            result = classify_message(case["message"])
            assert result.needs_human, case["id"]
            assert result.urgency in ("high", "critical"), case["id"]
