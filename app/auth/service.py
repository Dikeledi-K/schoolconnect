"""Staff accounts and login sessions. Plain functions (no HTTP) so they are easy to test.

Rules:
- 5 wrong passwords in a row lock the account for 15 minutes.
- A login gives a random bearer token that expires after 8 hours.
- Only the SHA-256 hash of a token is stored (like a password, but a token is long and
  random, so a fast hash is enough).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, verify_password
from app.models import Staff, StaffSession
from app.taxonomy import ACCOUNT_ROLES

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15
SESSION_HOURS = 8
MIN_PASSWORD_LENGTH = 10


class LoginError(Exception):
    """Login refused. `locked` tells the API to say "try again later"."""

    def __init__(self, message: str, locked: bool = False):
        super().__init__(message)
        self.locked = locked


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes (stored as UTC); make them comparable."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------
def create_staff(db: Session, name: str, email: str, role: str, password: str,
                 active: bool = True) -> Staff:
    if role not in ACCOUNT_ROLES:
        raise ValueError(f"Unknown role '{role}'. Choose one of: {', '.join(ACCOUNT_ROLES)}")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    email = email.strip().lower()
    if db.scalar(select(Staff).where(Staff.email == email)):
        raise ValueError(f"A staff account with email {email} already exists")
    staff = Staff(name=name.strip(), email=email, role=role, active=active,
                  password_hash=hash_password(password))
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return staff


def get_staff_by_email(db: Session, email: str) -> Staff | None:
    return db.scalar(select(Staff).where(Staff.email == email.strip().lower()))


# A hash of a random password: checked when the email is unknown, so a wrong email
# takes as long as a wrong password (an attacker cannot discover which emails exist).
_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_hex(16))
    return _DUMMY_HASH


def authenticate(db: Session, email: str, password: str, now: datetime | None = None) -> Staff:
    """Return the staff member, or raise LoginError. Counts failures and locks the account."""
    now = _now(now)
    staff = get_staff_by_email(db, email)
    if staff is None or not staff.active:
        verify_password(password, _dummy_hash())
        raise LoginError("Invalid email or password")

    locked_until = _aware(staff.locked_until)
    if locked_until and locked_until > now:
        raise LoginError("Too many failed logins. Try again in 15 minutes.", locked=True)

    if not verify_password(password, staff.password_hash):
        staff.failed_logins += 1
        if staff.failed_logins >= MAX_FAILED_LOGINS:
            staff.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            staff.failed_logins = 0
            db.commit()
            raise LoginError("Too many failed logins. Try again in 15 minutes.", locked=True)
        db.commit()
        raise LoginError("Invalid email or password")

    staff.failed_logins, staff.locked_until = 0, None
    db.commit()
    return staff


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------
def start_session(db: Session, staff: Staff, now: datetime | None = None) -> tuple[str, datetime]:
    """Create a login. Returns the token (shown once, never stored) and its expiry."""
    now = _now(now)
    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(hours=SESSION_HOURS)
    # Tidy up this person's expired sessions while we are here.
    db.execute(delete(StaffSession).where(StaffSession.staff_id == staff.id,
                                          StaffSession.expires_at < now))
    db.add(StaffSession(token_hash=token_hash(token), staff_id=staff.id, expires_at=expires_at))
    db.commit()
    return token, expires_at


def staff_for_token(db: Session, token: str, now: datetime | None = None) -> Staff | None:
    """The logged-in staff member, or None if the token is unknown, expired or the account is inactive."""
    now = _now(now)
    session = db.scalar(select(StaffSession).where(StaffSession.token_hash == token_hash(token)))
    if session is None or _aware(session.expires_at) <= now:
        return None
    staff = db.get(Staff, session.staff_id)
    return staff if staff is not None and staff.active else None


def end_session(db: Session, token: str) -> None:
    db.execute(delete(StaffSession).where(StaffSession.token_hash == token_hash(token)))
    db.commit()
