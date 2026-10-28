"""The outbox: one row per notification, whether or not it was really sent.

NOTIFY_MODE=dry_run (default): write the row, send nothing. Safe for demos and tests.
NOTIFY_MODE=smtp:              send email with smtplib (STARTTLS), record sent / failed.

Phone numbers get status "not_supported": SMS / WhatsApp would come later, and the staff
inbox tells staff to phone the parent instead.

The ticket's event timeline records THAT a notification was queued and its status, never the
recipient or the text.
"""

from __future__ import annotations

import re
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Outbox, Staff, Ticket
from app.privacy.pii import mask_pii
from app.workflow import events

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$")
PHONE_RE = re.compile(r"^[\d\s()+-]{9,20}$")


def channel_for(contact: str) -> str:
    contact = contact.strip()
    if EMAIL_RE.match(contact):
        return "email"
    if PHONE_RE.match(contact):
        return "phone"
    return "unknown"


def _send_smtp(settings: Settings, recipient: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)


def queue(db: Session, recipient: str, subject: str, body: str, *, kind: str,
          ticket_id: int | None = None, response_id: int | None = None,
          settings: Settings | None = None, now: datetime | None = None) -> Outbox:
    """Record (and in smtp mode, send) one notification. The caller commits."""
    settings = settings or get_settings()
    now = now or datetime.now(timezone.utc)
    channel = channel_for(recipient)
    row = Outbox(recipient=recipient.strip(), channel=channel, kind=kind, subject=subject, body=body,
                 ticket_id=ticket_id, response_id=response_id, created_at=now)
    if channel != "email":
        row.status = "not_supported"
        row.error = "Only email is supported for now (no SMS/WhatsApp). Please phone the parent."
    elif settings.notify_mode != "smtp":
        row.status = "dry_run"
    else:
        try:
            _send_smtp(settings, row.recipient, subject, body)
            row.status, row.sent_at = "sent", now
        except (OSError, smtplib.SMTPException) as err:
            # Mask the error text too: SMTP errors can echo the address back.
            row.status, row.error = "failed", mask_pii(str(err)).text[:300]
    db.add(row)
    if ticket_id is not None:
        events.log(db, ticket_id, "notified", kind, row.status, events.SYSTEM, at=now)
    return row


def notify_parent(db: Session, ticket: Ticket, subject: str, body: str, *, kind: str,
                  response_id: int | None = None) -> Outbox | None:
    """Notify the parent at the contact they gave. None if they gave no contact."""
    if not ticket.parent_contact:
        return None
    return queue(db, ticket.parent_contact, subject, body, kind=kind, ticket_id=ticket.id,
                 response_id=response_id)


def notify_staff(db: Session, staff: Staff, subject: str, body: str, *, kind: str,
                 ticket_id: int | None = None) -> Outbox:
    return queue(db, staff.email, subject, body, kind=kind, ticket_id=ticket_id)


def delivery_status(db: Session, response_id: int) -> str | None:
    """sent / dry_run / failed / not_supported for an approved reply, or None if never queued."""
    row = db.scalar(select(Outbox).where(Outbox.response_id == response_id).order_by(Outbox.id.desc()))
    return row.status if row else None


def for_ticket(db: Session, ticket_id: int) -> list[Outbox]:
    return list(db.scalars(select(Outbox).where(Outbox.ticket_id == ticket_id).order_by(Outbox.id)))
