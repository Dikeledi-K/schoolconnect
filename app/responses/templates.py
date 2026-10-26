"""Reply templates. Every fact comes from config/school_info.yaml, never from code or an AI.

A reply = greeting (tone) + body (category) + response promise (urgency) + closing (tone).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

SCHOOL_INFO_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "school_info.yaml"
TONES = ["formal", "friendly", "urgent"]


@lru_cache
def load_school_info(path: str = str(SCHOOL_INFO_FILE)) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def category_body(category: str, info: dict) -> str:
    """The factual middle part of a reply, per category."""
    s = info["school"]
    if category == "admissions":
        return ("Thank you for your message about admissions. These are the steps:\n"
                f"{_bullets(info['admissions']['steps'])}\n\n"
                f"Please bring certified copies of:\n{_bullets(info['admissions']['documents'])}")
    if category == "fees_exemptions":
        return ("Thank you for your message about school fees. "
                f"{info['fees']['statement_requests']} When paying, please use "
                f"{info['fees']['payment_reference']} as the reference.\n\n"
                "To apply for a fee exemption, please submit:\n"
                f"{_bullets(info['fees']['exemption_documents'])}")
    if category == "academic":
        return ("Thank you for your message about your child's schoolwork. "
                f"{info['academic']['reports']} {info['academic']['meetings']}")
    if category == "transport":
        return f"Thank you for your message about transport. {info['transport']['info']}"
    if category == "it_portal":
        return ("Thank you for letting us know about the problem with the portal. "
                f"{info['it_portal']['password_reset']}")
    return f"Thank you for your message to {s['name']}."


def acknowledgement_body(info: dict) -> str:
    """Learner welfare / safety: acknowledge only. A person handles everything else."""
    return ("Thank you for telling us. We take this very seriously. A senior staff member will "
            "contact you personally to discuss it.\n\n"
            f"{info['emergency']}")


def build_reply(category: str, urgency: str, tone: str, reference: str,
                acknowledgement_only: bool, info: dict | None = None) -> str:
    info = info or load_school_info()
    s = info["school"]
    greeting = "Hello," if tone == "friendly" else "Dear Parent/Guardian,"
    opening = "We have marked your message as urgent.\n\n" if tone == "urgent" else ""
    body = acknowledgement_body(info) if acknowledgement_only else category_body(category, info)
    promise = (f"Your reference number is {reference}. We will respond "
               f"{info['response_times'][urgency]}. You can also contact the office on {s['phone']} "
               f"or {s['email']} ({s['office_hours']}).")
    closing = (f"Thank you,\nThe {s['name']} team" if tone == "friendly"
               else f"Kind regards,\n{s['name']} office")
    return f"{greeting}\n\n{opening}{body}\n\n{promise}\n\n{closing}"


def facts_text(info: dict | None = None) -> str:
    """All school facts as one text, used to check that an AI reply adds nothing new."""
    return yaml.safe_dump(info or load_school_info(), allow_unicode=True)
