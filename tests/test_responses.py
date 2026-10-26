"""Week 6: reply drafts (templates, grounding check, welfare acknowledgement)."""

from types import SimpleNamespace
from unittest.mock import patch

from app.config import Settings
from app.responses.generator import generate_draft, grounding_problems
from app.responses.templates import build_reply, facts_text, load_school_info

AI_SETTINGS = Settings(llm_provider="anthropic", anthropic_api_key="test-key")
INFO = load_school_info()


def ticket(**overrides):
    base = dict(category="fees_exemptions", urgency="medium", reference="SC-20260301-0004",
                language="en", safety_flag=False, message="Please send my fee statement, Thandi, 082 123 4567",
                parent_name="Thandi")
    return SimpleNamespace(**{**base, **overrides})


def test_template_uses_only_school_facts():
    reply = build_reply("fees_exemptions", "medium", "formal", "SC-20260301-0004", False)
    assert INFO["school"]["phone"] in reply and INFO["school"]["email"] in reply
    assert INFO["response_times"]["medium"] in reply and "SC-20260301-0004" in reply
    for document in INFO["fees"]["exemption_documents"]:
        assert document in reply
    # Every number in the template is a known fact (nothing invented in code).
    assert grounding_problems(reply, facts_text() + "SC-20260301-0004") == []


def test_tones_differ():
    replies = {tone: build_reply("academic", "low", tone, "SC-1", False) for tone in ("formal", "friendly", "urgent")}
    assert replies["formal"].startswith("Dear Parent/Guardian") and replies["friendly"].startswith("Hello")
    assert "marked your message as urgent" in replies["urgent"]
    assert len(set(replies.values())) == 3


def test_welfare_is_acknowledgement_only_and_never_sent_to_ai():
    with patch("app.responses.generator.generate_text") as llm:
        draft = generate_draft(ticket(category="learner_welfare", urgency="high"), "friendly", AI_SETTINGS)
    llm.assert_not_called()
    assert draft.acknowledgement_only and draft.method == "template"
    assert INFO["emergency"] in draft.body and "senior staff member" in draft.body


def test_safety_flag_on_any_category_is_acknowledgement_only():
    draft = generate_draft(ticket(category="transport", safety_flag=True), "formal", AI_SETTINGS)
    assert draft.acknowledgement_only


def test_ai_reply_accepted_when_grounded_and_input_masked():
    good = (f"Hello! Please contact the office on {INFO['school']['phone']}. "
            "Your reference number is SC-20260301-0004.")
    with patch("app.responses.generator.generate_text", return_value=good) as llm:
        draft = generate_draft(ticket(language="zu"), "friendly", AI_SETTINGS)
    sent = llm.call_args.args[1]
    assert "082 123 4567" not in sent and "Thandi" not in sent and "[PHONE]" in sent
    assert draft.llm_used and draft.method == "anthropic" and draft.body == good
    assert draft.pii_found == {"phone": 1, "name": 1}


def test_ai_reply_with_invented_fact_falls_back_to_template():
    with patch("app.responses.generator.generate_text", return_value="Pay R2500 to account 1234567890 now."):
        draft = generate_draft(ticket(language="af"), "formal", AI_SETTINGS)
    assert not draft.llm_used and draft.method == "template"
    assert draft.fallback_reason.startswith("AI reply rejected") and "2500" in draft.fallback_reason
    assert any("translat" in n for n in draft.notes)   # staff told it is in English


def test_ai_failure_falls_back_to_template():
    with patch("app.responses.generator.generate_text", return_value=None):
        draft = generate_draft(ticket(), "formal", AI_SETTINGS)
    assert draft.method == "template" and draft.fallback_reason == "LLM unavailable or failed"


def test_rules_mode_uses_template_without_ai_call():
    with patch("app.responses.generator.generate_text") as llm:
        draft = generate_draft(ticket(language="st"), "formal", Settings(llm_provider="rules"))
    llm.assert_not_called()
    assert draft.method == "template" and draft.fallback_reason is None
    assert any("Sesotho" in n for n in draft.notes)
