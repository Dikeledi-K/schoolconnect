"""Find and mask personal information (PII) before text leaves the school's systems.

Used before EVERY LLM call and on every log line (POPIA: share only what is necessary).

What is masked, in this order (order matters: an email can contain digits):
  [EMAIL]      name@example.co.za
  [ID_NUMBER]  South African ID: 13 digits, a real YYMMDD birth date, and a valid Luhn check digit
  [PHONE]      SA numbers: 082 123 4567, 011-555-1234, +27 82 123 4567, 0027821234567
  [NUMBER]     any other run of 10+ digits (e.g. a bank account or an ID with a typo)
  [NAME]       each word of names we already know (e.g. the parent_name field)

Limits (documented in docs/POPIA.md): names that we were not told about, such as a learner's
name inside the message, cannot be detected reliably by rules. Staff see the original message;
only external services get the masked version.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
# 13 digits, optionally grouped as 6-4-2-1 or 6-7 with spaces (e.g. "800101 5009 087").
ID_RE = re.compile(r"(?<!\d)(\d{6})[ ]?(\d{4})[ ]?(\d{2})[ ]?(\d)(?!\d)")
# +27 / 0027 / 27 / 0, then a 2-digit area or network code, then 7 digits (spaces, dashes allowed).
PHONE_RE = re.compile(r"(?<![\w+])(?:\+27|0027|27|0)[ -]?\(?[1-9]\d\)?[ -]?\d{3}[ -]?\d{4}(?!\d)")
# Not preceded by "SC-": ticket references like SC-20260122-0007 are not personal data.
LONG_NUMBER_RE = re.compile(r"(?<!\d)(?<!SC-)\d(?:[ -]?\d){9,}(?!\d)")


@dataclass
class MaskResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def found(self) -> bool:
        return any(self.counts.values())


def luhn_valid(digits: str) -> bool:
    """Luhn check digit test (used by SA ID numbers and bank cards)."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:          # double every second digit from the right
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def is_sa_id_number(digits: str) -> bool:
    """13 digits, starts with a real date of birth (YYMMDD), citizenship digit 0-2, valid Luhn."""
    if len(digits) != 13 or not digits.isdigit():
        return False
    yy, mm, dd = int(digits[0:2]), int(digits[2:4]), int(digits[4:6])
    for century in (1900, 2000):          # the century is not stored, so try both
        try:
            date(century + yy, mm, dd)
            break
        except ValueError:
            continue
    else:
        return False
    return digits[10] in "012" and luhn_valid(digits)


def mask_pii(text: str, names: list[str] | tuple[str, ...] | None = None) -> MaskResult:
    """Return the text with personal information replaced by placeholders, plus counts per type."""
    if not text:
        return MaskResult(text or "", {})
    counts = {"email": 0, "id_number": 0, "phone": 0, "number": 0, "name": 0}

    def sub(pattern, label, key, check=None):
        nonlocal text

        def repl(m):
            if check and not check(m):
                return m.group(0)
            counts[key] += 1
            return label

        text = pattern.sub(repl, text)

    sub(EMAIL_RE, "[EMAIL]", "email")
    sub(ID_RE, "[ID_NUMBER]", "id_number", check=lambda m: is_sa_id_number("".join(m.groups())))
    sub(PHONE_RE, "[PHONE]", "phone")
    sub(LONG_NUMBER_RE, "[NUMBER]", "number")

    # Known names: mask each word of 2+ letters, whole words only, any capitalisation.
    words = {w for n in (names or []) if n for w in re.findall(r"[^\W\d_]{2,}", n)}
    for word in sorted(words, key=len, reverse=True):
        pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        text, n = pattern.subn("[NAME]", text)
        counts["name"] += n

    return MaskResult(text, {k: v for k, v in counts.items() if v})


class PIIRedactingFilter(logging.Filter):
    """Logging filter: masks PII in every log line before it is written anywhere."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging
            return True
        record.msg = mask_pii(message).text
        record.args = ()
        return True


_installed = False


def install_log_redaction() -> None:
    """Mask PII in EVERY log record, whichever logger or handler it goes to.

    We wrap Python's log-record factory, so a record is masked the moment it is created.
    This also covers loggers and handlers set up later (e.g. by uvicorn). Safe to call twice.
    """
    global _installed
    if _installed:
        return
    original_factory = logging.getLogRecordFactory()
    redactor = PIIRedactingFilter()

    def factory(*args, **kwargs):
        record = original_factory(*args, **kwargs)
        redactor.filter(record)
        return record

    logging.setLogRecordFactory(factory)
    _installed = True
