"""Rule-based classifier: keyword matching, categories, language, urgency."""

import pytest

from app.classifier.rules import (
    classify_with_rules,
    detect_language,
    find_keywords,
    find_safety_terms,
    normalise,
)


def test_normalise_removes_apostrophes_and_case():
    assert normalise("Didn’t  COME home") == "didnt come home"


@pytest.mark.parametrize("text, keyword, lang, expected", [
    ("payments are late", "payment", "en", True),    # 5+ chars: prefix match
    ("please apply now", "app", "en", False),        # short: whole word only
    ("the app crashed", "app", "en", True),
    ("my business", "bus", "en", False),
    ("ngemali yesikole", "mali", "zu", True),        # isiZulu stem inside a word
    ("message for you", "mes", "af", False),
])
def test_keyword_matching_rules(text, keyword, lang, expected):
    assert bool(find_keywords(normalise(text), {lang: [keyword]})) is expected


@pytest.mark.parametrize("message, category", [
    ("How do I apply for Grade 1 registration?", "admissions"),
    ("I paid the school fees but the statement is wrong", "fees_exemptions"),
    ("When will report cards and exam results come out?", "academic"),
    ("My child is being bullied at school", "learner_welfare"),
    ("The school bus did not pick up my son", "transport"),
    ("I forgot my password for the parent portal", "it_portal"),
    ("Where do I buy the uniform?", "other"),
    ("Ngicela ukukhokha imali yesikole", "fees_exemptions"),      # isiZulu
    ("Ke kopa ho ngodisa ngwanaka", "admissions"),                # Sesotho
    ("Wanneer is die eksamen?", "academic"),                      # Afrikaans
])
def test_categories(message, category):
    assert classify_with_rules(message).category == category


@pytest.mark.parametrize("message, language", [
    ("Hello, when is the school concert?", "en"),
    ("Sawubona, ngicela usizo ngengane yami", "zu"),
    ("Dumela, ke kopa ho tseba hore sekolo se bula neng", "st"),
    ("Goeie more, ek wil graag weet wanneer die skool begin", "af"),
    ("Molo, ndicela uncedo ngomntwana wam", "xh"),
    ("12345 ???", "unknown"),
])
def test_language_detection(message, language):
    assert detect_language(message) == language


def test_code_switched_message_picks_non_english():
    # Mostly isiZulu with English school words.
    assert detect_language("Sawubona, ngicela ukwazi nge report ka grade 5 yengane yami") == "zu"


def test_deadline_words_raise_urgency():
    assert classify_with_rules("Fee exemption deadline is tomorrow, urgent").urgency == "high"


def test_relaxed_enquiry_is_low():
    assert classify_with_rules("Just wondering when sports day is").urgency == "low"


def test_no_keywords_defaults_to_other_with_low_confidence():
    result = classify_with_rules("hello there")
    assert result.category == "other"
    assert result.confidence < 0.35


def test_safety_terms_found():
    critical, high = find_safety_terms("My son didn't come home and he was bullied")
    assert "didnt come home" in critical
    assert "bullied" in high


def test_rules_never_set_human_flags_themselves():
    # Rules only classify; the guardrails in service.py decide safety flags.
    result = classify_with_rules("My child is being bullied")
    assert result.method == "rules"
    assert result.needs_human is False
