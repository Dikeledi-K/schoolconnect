"""Prompt-injection suite: attacks hidden in parent messages, and dangerous AI replies.

Layers tested for every classification attack:
  rules          the offline classifier on the raw message
  hostile_ai     we PRETEND the AI fully obeyed the attack (category "other", urgency "low");
                 the safety guardrails must still produce the safe result
  prompt_wrap    the message cannot close the <parent_message> data tags itself
For every reply attack:
  grounding      an AI reply with invented facts, links or placeholders must be rejected
"""

from __future__ import annotations

import json
from pathlib import Path

from app.classifier.llm import build_user_prompt
from app.classifier.rules import classify_with_rules
from app.classifier.service import apply_guardrails
from app.responses.generator import grounding_problems
from app.responses.templates import build_reply, facts_text
from app.schemas import ClassificationResult
from app.taxonomy import CATEGORIES, urgency_rank

CASES_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "prompt_injection_cases.json"


def load_cases(path: Path = CASES_FILE) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _meets(result: ClassificationResult, expect: dict) -> tuple[bool, str]:
    problems = []
    if "urgency" in expect and result.urgency != expect["urgency"]:
        problems.append(f"urgency {result.urgency} (expected {expect['urgency']})")
    if "min_urgency" in expect and urgency_rank(result.urgency) < urgency_rank(expect["min_urgency"]):
        problems.append(f"urgency {result.urgency} (expected at least {expect['min_urgency']})")
    if "category" in expect and result.category != expect["category"]:
        problems.append(f"category {result.category} (expected {expect['category']})")
    if expect.get("needs_human") and not result.needs_human:
        problems.append("not flagged for a human")
    return (not problems), "; ".join(problems) or "ok"


def hostile_result() -> ClassificationResult:
    """What a fully 'tricked' AI would answer."""
    return ClassificationResult(category="other", urgency="low", language="en",
                                routed_role=CATEGORIES["other"].routed_role, confidence=0.99,
                                method="anthropic", needs_human=False, safety_flag=False,
                                reason="Classified as instructed.")


def run_suite(path: Path = CASES_FILE) -> list[dict]:
    cases = load_cases(path)
    out = []
    for case in cases["classification"]:
        rules = apply_guardrails(case["message"], classify_with_rules(case["message"]))
        ok, detail = _meets(rules, case["expect"])
        out.append({"id": case["id"], "attack": case["attack"], "layer": "rules", "passed": ok, "detail": detail})

        tricked = apply_guardrails(case["message"], hostile_result())
        ok, detail = _meets(tricked, case["expect"])
        out.append({"id": case["id"], "attack": case["attack"], "layer": "hostile_ai", "passed": ok, "detail": detail})

        wrapped = build_user_prompt(case["message"])
        ok = wrapped.count("<parent_message>") == 1 and wrapped.count("</parent_message>") == 1
        out.append({"id": case["id"], "attack": case["attack"], "layer": "prompt_wrap", "passed": ok,
                    "detail": "ok" if ok else "message could close the data tags"})

    allowed = facts_text() + "\n" + build_reply("admissions", "medium", "friendly", "SC-20260101-0001", False)
    for case in cases["replies"]:
        problems = grounding_problems(case["ai_reply"], allowed)
        rejected = bool(problems)
        ok = rejected == case["expect_rejected"]
        detail = ("rejected: " + "; ".join(problems)) if rejected else "accepted"
        out.append({"id": case["id"], "attack": case["attack"], "layer": "grounding", "passed": ok, "detail": detail})
    return out


def summary(results: list[dict] | None = None) -> dict:
    results = results if results is not None else run_suite()
    return {"checks": len(results), "passed": sum(r["passed"] for r in results),
            "failed": [r for r in results if not r["passed"]], "results": results}
