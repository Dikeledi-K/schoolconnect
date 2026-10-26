"""Week 6: PII masking and log redaction."""

import logging
from unittest.mock import patch

import pytest

from app.classifier import classify_message
from app.privacy.pii import install_log_redaction, is_sa_id_number, luhn_valid, mask_pii

VALID_ID = "8001015009087"   # synthetic: valid date (1980-01-01) and Luhn check digit


def test_luhn_and_sa_id_rules():
    assert luhn_valid(VALID_ID)
    assert is_sa_id_number(VALID_ID)
    assert not is_sa_id_number("8001015009088")    # wrong check digit
    assert not is_sa_id_number("8013015009087")    # month 13 is not a date
    assert not is_sa_id_number("12345")


@pytest.mark.parametrize("text,label", [
    (f"My ID is {VALID_ID}", "[ID_NUMBER]"),
    ("ID: 800101 5009 087", "[ID_NUMBER]"),
    ("cell 082 123 4567", "[PHONE]"),
    ("phone 011-555-1234", "[PHONE]"),
    ("whatsapp +27 82 123 4567", "[PHONE]"),
    ("or 0027821234567", "[PHONE]"),
    ("email thandi.m@gmail.com", "[EMAIL]"),
    ("account 62001234567", "[NUMBER]"),
])
def test_masks_each_type(text, label):
    result = mask_pii(text)
    assert label in result.text and result.found


def test_school_facts_and_small_numbers_are_not_masked():
    text = "Grade 10 fees are R1500 for 2026; reference SC-20260122-0007."
    assert mask_pii(text).text == text


def test_known_names_masked_case_insensitively():
    result = mask_pii("Thandi Mokoena here. Mrs MOKOENA again.", names=["Thandi Mokoena"])
    assert result.text == "[NAME] [NAME] here. Mrs [NAME] again."
    assert result.counts == {"name": 3}


def test_classifier_sends_only_masked_text_to_llm():
    seen = {}

    def fake_llm(text, settings):
        seen["text"] = text
        return None   # behave as if the AI failed, so rules are used

    with patch("app.classifier.service.classify_with_llm", side_effect=fake_llm):
        result = classify_message(f"Hi, Thandi here, ID {VALID_ID}, call 082 123 4567. Fee statement please",
                                  names=["Thandi"])
    assert VALID_ID not in seen["text"] and "082 123 4567" not in seen["text"] and "Thandi" not in seen["text"]
    assert "[ID_NUMBER]" in seen["text"] and "[PHONE]" in seen["text"] and "[NAME]" in seen["text"]
    assert result.category == "fees_exemptions"   # the rules still saw the real text


def test_masking_never_weakens_safety():
    # Guardrails run on the ORIGINAL text, so a masked AI input cannot hide danger.
    result = classify_message("My son is missing. Call me on 082 123 4567", names=["Sipho"])
    assert result.urgency == "critical" and result.needs_human


def test_log_lines_are_redacted(caplog):
    install_log_redaction()
    install_log_redaction()   # safe to call twice
    with caplog.at_level(logging.INFO):
        logging.getLogger("app.test").info("parent called from %s, id %s", "082 123 4567", VALID_ID)
    line = caplog.records[-1].getMessage()
    assert "082 123 4567" not in line and VALID_ID not in line
    assert "[PHONE]" in line and "[ID_NUMBER]" in line
