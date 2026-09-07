"""
Shared Auth Token Service — JWT creation, verification, refresh, and revocation.

Handles:
- Access token (JWT) creation and verification
- Refresh token generation (persistence handled by UserRepository in PostgreSQL)
- In-process token blacklist for logout (no Redis required in pilot/local runs)

Note: The pilot/local deployment does NOT run Redis, so revoked JWT ids are kept
in a module-level dict shared by every TokenService instance in this gateway
process. Refresh-token persistence & validation live in iam.refresh_tokens via
UserRepository.
"""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from shared.auth.models import TokenResponse, UserContext
from shared.config.settings import settings

# In-process blacklist of revoked JWT ids: jti -> expiry timestamp (epoch).
# Shared module-level so every TokenService instance (middleware + routes) sees
# the same revocations. Cleared when the gateway process restarts.
_JWT_BLACKLIST: dict[str, float] = {}


class TokenService:
    """JWT token lifecycle management with an in-process revocation blacklist.

    The pilot/local deployment has no Redis, so revocations are kept in a
    module-level dict shared by every TokenService instance in this process.
    Refresh-token persistence/validation is handled by UserRepository
    (PostgreSQL) — see gateway/routes/auth_routes.py.
    """

    def __init__(self, redis_client=None) -> None:  # noqa: ANN001 - legacy arg, ignored
        """Initialize token service.

        Args:
            redis_client: Deprecated. Kept for call-site compatibility; ignored.
        """
        self._redis = None

    # ------------------------------------------------------------------
    # Access Tokens (JWT)
    # ------------------------------------------------------------------

    def create_access_token(self, user: UserContext) -> str:
        """Create a signed JWT access token for a user.

        Args:
            user: Authenticated user context.

        Returns:
            Signed JWT string.
        """
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user.user_id),
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "roles": user.roles,
            "branch_code": user.branch_code,
            "iat": now,
            "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
            "jti": str(uuid.uuid4()),
            "type": "access",
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def decode_access_token(self, token: str) -> dict:
        """Decode and verify a JWT access token.

        Args:
            token: Raw JWT string.

        Returns:
            Decoded payload dict.

        Raises:
            InvalidTokenError: If the token is invalid, expired, or blacklisted.
        """
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "jti", "type"]},
        )
        if payload.get("type") != "access":
            raise InvalidTokenError("Token is not an access token")
        return payload

    async def is_blacklisted(self, jti: str) -> bool:
        """Check if a JWT ID is in the in-process blacklist.

        Args:
            jti: JWT ID from token payload.

        Returns:
            True if the token has been revoked and is still within its TTL.
        """
        if not jti:
            return False
        expiry = _JWT_BLACKLIST.get(jti)
        if expiry is None:
            return False
        if time.time() > expiry:
            _JWT_BLACKLIST.pop(jti, None)
            return False
        return True

    async def blacklist_token(self, jti: str, ttl_seconds: int = 900) -> None:
        """Add a JWT ID to the in-process blacklist.

        Args:
            jti: JWT ID to blacklist.
            ttl_seconds: Time-to-live matching the token's remaining lifetime.
        """
        if jti:
            _JWT_BLACKLIST[jti] = time.time() + max(int(ttl_seconds), 1)

    # ------------------------------------------------------------------
    # Refresh Tokens
    # ------------------------------------------------------------------

    def create_refresh_token(self, user_id: uuid.UUID) -> tuple[str, str]:
        """Create a new refresh token.

        Args:
            user_id: The user this refresh token belongs to.

        Returns:
            Tuple of (raw_refresh_token, token_hash).
        """
        raw = secrets.token_urlsafe(64)
        token_hash = self._hash(raw)
        return raw, token_hash

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hash(value: str) -> str:
        """SHA-256 hash a string."""
        return hashlib.sha256(value.encode()).hexdigest()
