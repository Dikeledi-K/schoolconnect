"""classify_message(): the one function the rest of the app calls.

Flow:
    message
      -> PII masked (Week 6) -> LLM (if configured)  --fails/invalid-->  rules
      -> safety guardrails (can only RAISE urgency, never lower it)
      -> ClassificationResult
"""

from __future__ import annotations

from app.classifier.llm import classify_with_llm
from app.classifier.rules import classify_with_rules, find_safety_terms
from app.config import Settings, get_settings
from app.privacy.pii import mask_pii
from app.schemas import ClassificationResult
from app.taxonomy import CATEGORIES, WELFARE_CATEGORY, max_urgency

# Below this confidence a person should double-check the category.
LOW_CONFIDENCE_THRESHOLD = 0.35


def classify_message(message: str, settings: Settings | None = None,
                     names: list[str] | None = None) -> ClassificationResult:
    """Classify a parent message.

    names: names we already know (e.g. the parent_name field), masked along with IDs, phone
    numbers and emails before anything is sent to an LLM. The rules classifier and the safety
    guardrails run locally on the original text, so masking never weakens child safety.
    """
    settings = settings or get_settings()

    llm_answer = classify_with_llm(mask_pii(message, names).text, settings)
    if llm_answer is not None:
        category = llm_answer["category"]
        result = ClassificationResult(
            category=category,
            urgency=llm_answer["urgency"],
            language=llm_answer["language"],
            routed_role=CATEGORIES[category].routed_role,
            confidence=llm_answer["confidence"],
            method=settings.llm_provider,
            needs_human=False,
            safety_flag=False,
            reason=llm_answer["reason"],
        )
    else:
        result = classify_with_rules(message)

    return apply_guardrails(message, result)


def apply_guardrails(message: str, result: ClassificationResult) -> ClassificationResult:
    """Child-safety and quality rules applied to EVERY result (rules or LLM).

    These checks look at the raw message text, so an LLM cannot talk its way
    past them. Each one can only make the outcome MORE cautious.
    """
    applied: list[str] = []
    critical_terms, high_terms = find_safety_terms(message)

    # G1: a child may be in danger -> critical, welfare, human required.
    if critical_terms:
        if result.urgency != "critical":
            applied.append("safety_critical_urgency")
        result.urgency = "critical"
        if result.category != WELFARE_CATEGORY:
            applied.append("safety_category_welfare")
            result.category = WELFARE_CATEGORY
        result.safety_flag = True
        result.needs_human = True
        result.reason += f" Safety terms: {', '.join(critical_terms)}."

    # G2: wellbeing concern -> at least high, human required.
    # The category is NOT changed (e.g. "scared about fee arrears" stays a fees ticket).
    elif high_terms:
        new_urgency = max_urgency(result.urgency, "high")
        if new_urgency != result.urgency:
            applied.append("safety_high_urgency")
        result.urgency = new_urgency
        result.safety_flag = True
        result.needs_human = True
        result.reason += f" Wellbeing terms: {', '.join(high_terms)}."

    # G3: anything classified as welfare is at least high and always human-handled.
    if result.category == WELFARE_CATEGORY:
        new_urgency = max_urgency(result.urgency, "high")
        if new_urgency != result.urgency:
            applied.append("welfare_min_high")
        result.urgency = new_urgency
        result.safety_flag = True
        result.needs_human = True

    # G4: unsure about the category -> a person should check it.
    if result.confidence < LOW_CONFIDENCE_THRESHOLD and not result.needs_human:
        applied.append("low_confidence_review")
        result.needs_human = True

    # Routing always follows the FINAL category.
    result.routed_role = CATEGORIES[result.category].routed_role
    result.reason = result.reason.strip()
    result.guardrails_applied = applied
    return result
