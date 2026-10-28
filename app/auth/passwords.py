"""Password hashing with the Python standard library only (no extra packages).

PBKDF2-HMAC-SHA256 with a random 16-byte salt per user. The stored text records the
algorithm, the iteration count, the salt and the hash, so we can raise the iteration
count later without breaking old passwords:

    pbkdf2_sha256$600000$<salt hex>$<hash hex>
"""

from __future__ import annotations

import hashlib
import secrets

from app.config import get_settings

ALGORITHM = "pbkdf2_sha256"


def _derive(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def hash_password(password: str, iterations: int | None = None) -> str:
    iterations = iterations or get_settings().password_hash_iterations
    salt = secrets.token_bytes(16)
    return f"{ALGORITHM}${iterations}${salt.hex()}${_derive(password, salt, iterations).hex()}"


def verify_password(password: str, stored: str) -> bool:
    """True if the password matches. compare_digest takes the same time whether the first
    or the last byte differs, so an attacker cannot learn the hash from timing."""
    try:
        algorithm, iterations, salt_hex, hash_hex = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        candidate = _derive(password, bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(candidate.hex(), hash_hex)
