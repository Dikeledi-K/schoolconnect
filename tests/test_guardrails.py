"""Child-safety guardrails: they must apply to rules AND LLM answers, and only raise urgency."""

import pytest

from app.classifier import llm as llm_module
from app.classifier.service import apply_guardrails, classify_message
from app.config import Settings
from app.schemas import ClassificationResult


def make_result(**overrides) -> ClassificationResult:
    base = dict(
        category="academic", urgency="low", language="en", routed_role="class_teacher",
        confidence=0.9, method="test", needs_human=False, safety_flag=False, reason="test",
    )
    base.update(overrides)
    return ClassificationResult(**base)


@pytest.mark.parametrize("message", [
    "My daughter says a teacher touched her inappropriately",
    "my son didnt come home from school",
    "Someone threatened him with a knife at break",
    "Umntwana wam uthi ufuna ukuzibulala",          # isiXhosa: wants to kill himself
    "Ingane yami ilahlekile kusukela izolo",        # isiZulu: is missing since yesterday
    "Iemand het my seun met n mes gedreig",         # Afrikaans: threatened with a knife
])
def test_critical_messages_are_critical_welfare_and_human(message):
    result = classify_message(message)
    assert result.urgency == "critical"
    assert result.category == "learner_welfare"
    assert result.routed_role == "deputy_principal"
    assert result.needs_human and result.safety_flag


@pytest.mark.parametrize("message", [
    "My child is being bullied every day",
    "He was injured during PE",
    "Ngwanaka o shapuwa ke bana ba bang",           # Sesotho: is being beaten
])
def test_wellbeing_messages_are_at_least_high(message):
    result = classify_message(message)
    assert result.urgency in ("high", "critical")
    assert result.needs_human


def test_guardrail_cannot_lower_urgency():
    result = apply_guardrails("My child is being bullied", make_result(urgency="critical"))
    assert result.urgency == "critical"


def test_guardrail_overrides_llm_that_ignored_danger():
    # Pretend an LLM said "academic, low" for a message about a missing child.
    result = apply_guardrails("My son went missing after school", make_result())
    assert result.urgency == "critical"
    assert result.category == "learner_welfare"
    assert "safety_critical_urgency" in result.guardrails_applied
    assert "safety_category_welfare" in result.guardrails_applied


def test_welfare_category_is_always_high_and_human():
    result = apply_guardrails("concern about my child", make_result(category="learner_welfare"))
    assert result.urgency == "high"
    assert result.needs_human


def test_wellbeing_term_keeps_original_category():
    result = apply_guardrails("I am scared about the fee arrears", make_result(category="fees_exemptions"))
    assert result.category == "fees_exemptions"
    assert result.urgency == "high"


def test_low_confidence_needs_human():
    result = apply_guardrails("hello", make_result(confidence=0.2, category="other"))
    assert result.needs_human
    assert "low_confidence_review" in result.guardrails_applied


def test_guardrails_apply_to_llm_results(monkeypatch):
    """A (mocked) LLM says 'other/low' for an abuse report: guardrails must still fire."""
    monkeypatch.setattr(
        llm_module, "_call_anthropic",
        lambda message, settings: '{"category":"other","urgency":"low","language":"en",'
                                  '"confidence":0.99,"reason":"general"}',
    )
    settings = Settings(llm_provider="anthropic", anthropic_api_key="test-key")
    result = classify_message("A boy has a gun in his school bag", settings)
    assert result.method == "anthropic"
    assert result.urgency == "critical"
    assert result.category == "learner_welfare"
