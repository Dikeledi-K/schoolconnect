"""Signed webhooks: how an email forwarder or WhatsApp gateway proves a request is genuine.

The sender and SchoolConnect share a secret (INBOUND_SECRET). For each request the sender sends:

    X-Timestamp: 1772438400                       (Unix seconds, now)
    X-Signature: sha256=<hex HMAC-SHA256 of "<timestamp>.<raw body>" with the secret>

We recompute the HMAC and compare with compare_digest (constant time). The timestamp is part
of what is signed, so an attacker cannot reuse an old signature with a fresh timestamp; and a
request older than 5 minutes is refused, so a captured request cannot be replayed later.
(This is the same scheme Stripe and Slack use.) See docs/INTEGRATIONS.md.
"""

from __future__ import annotations

import hashlib
import hmac
import time

MAX_AGE_SECONDS = 300


class InboundAuthError(Exception):
    """The request is not genuine (or too old). Always answered with 401."""


def sign(secret: str, timestamp: str, body: bytes) -> str:
    message = timestamp.encode("ascii") + b"." + body
    return "sha256=" + hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify(secret: str, timestamp: str | None, signature: str | None, body: bytes,
           now: float | None = None, max_age: int = MAX_AGE_SECONDS) -> None:
    """Raise InboundAuthError unless the signature is valid and the timestamp is recent."""
    if not timestamp or not signature:
        raise InboundAuthError("Missing X-Timestamp or X-Signature header")
    try:
        sent_at = int(timestamp)
    except ValueError:
        raise InboundAuthError("X-Timestamp must be Unix seconds")
    now = time.time() if now is None else now
    if abs(now - sent_at) > max_age:
        raise InboundAuthError("Request too old (or clock wrong): timestamps must be within 5 minutes")
    expected = sign(secret, timestamp, body)
    if not hmac.compare_digest(expected, signature.strip()):
        raise InboundAuthError("Invalid signature")
