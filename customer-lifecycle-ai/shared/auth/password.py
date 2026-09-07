"""
Local password hashing & verification (stdlib only — no external deps).

Format of a stored hash:
    pbkdf2_sha256$<iterations>$<salt_hex>$<digest_hex>

Seeded by scripts/seed_iam.py and verified by the gateway local-auth login path.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from shared.config.settings import settings

_ALGORITHM = "pbkdf2_sha256"


def hash_password(password: str, *, iterations: int | None = None) -> str:
    """Return a salted pbkdf2_sha256 hash string for the given password."""
    iterations = iterations or settings.password_hash_iterations
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), iterations
    )
    return f"{_ALGORITHM}${iterations}${salt}${digest.hex()}"


def _parse(encoded: str) -> tuple[int, str, str]:
    parts = encoded.split("$")
    if len(parts) != 4 or parts[0] != _ALGORITHM:
        raise ValueError("Unsupported password hash format")
    return int(parts[1]), parts[2], parts[3]


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time verification of a password against a stored hash."""
    try:
        iterations, salt, digest = _parse(encoded)
    except (ValueError, IndexError):
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), iterations
    )
    return hmac.compare_digest(candidate.hex(), digest)
