"""The text of every notification. Facts come only from config/school_info.yaml.

POPIA rule for STAFF alerts: email can be forwarded, read on shared phones or leak, so a staff
alert contains only the reference, category, urgency and response deadline - never the
message text or the parent's details. Learner-welfare alerts say even less: only that there
is a welfare ticket and its reference. Staff open SchoolConnect (behind a login) to read more.

Every function returns (subject, body).
"""

from __future__ import annotations

from app.auth.access import is_welfare
from app.models import Ticket
from app.responses.templates import load_school_info
from app.taxonomy import CATEGORIES

STAFF_REASONS = {
    "assigned": "assigned to you",
    "escalated": "escalated to you",
    "new_critical": "NEW CRITICAL ticket",
    "critical_unacknowledged": "CRITICAL ticket not yet acknowledged",
}


def staff_alert(ticket: Ticket, reason: str, due_text: str | None = None) -> tuple[str, str]:
    """Alert for a staff member. `reason` is a key of STAFF_REASONS."""
    what = STAFF_REASONS[reason]
    if is_welfare(ticket):
        # Welfare: the reference only. Nothing about the child or what happened.
        prefix = "Escalated" if reason == "escalated" else "New"
        return (f"SchoolConnect: learner welfare ticket {ticket.reference}",
                f"{prefix} learner welfare ticket {ticket.reference}, open SchoolConnect.")
    lines = [
        f"Ticket {ticket.reference}: {what}.",
        "",
        f"Category: {CATEGORIES[ticket.category].display_name}",
        f"Urgency: {ticket.urgency}",
    ]
    if due_text:
        lines.append(f"Response due: {due_text}")
    lines += ["", "Open SchoolConnect to read the message."]
    return f"SchoolConnect: {ticket.reference} {what}", "\n".join(lines)


def parent_reply(ticket: Ticket, reply_body: str, info: dict | None = None) -> tuple[str, str]:
    """The staff-approved reply itself (written from school facts in Week 6)."""
    info = info or load_school_info()
    return f"Reply from {info['school']['name']} ({ticket.reference})", reply_body


def parent_resolved(ticket: Ticket, info: dict | None = None) -> tuple[str, str]:
    info = info or load_school_info()
    s = info["school"]
    body = (f"Dear Parent/Guardian,\n\n"
            f"Your message with reference {ticket.reference} has been marked as resolved.\n\n"
            f"If you still need help, please contact the office on {s['phone']} or {s['email']} "
            f"({s['office_hours']}) and quote your reference number.\n\n"
            f"Kind regards,\n{s['name']} office")
    return f"Your message {ticket.reference} is resolved", body
