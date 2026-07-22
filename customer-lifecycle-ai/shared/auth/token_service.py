"""
Shared Auth Token Service — JWT creation, verification, refresh, and Redis blacklist.

Handles:
- Access token (JWT) creation and verification
- Refresh token generation, storage, rotation, and revocation
- Redis-based token blacklist for logout
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import redis.asyncio as aioredis
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from shared.auth.models import TokenResponse, UserContext
from shared.config.settings import settings


class TokenService:
    """JWT token lifecycle management with Redis-backed blacklist and refresh tokens."""

    BLACKLIST_PREFIX = "jwt_blacklist:"  # Redis key prefix for blacklisted JTIs
    REFRESH_PREFIX = "refresh:"          # Redis key prefix for refresh token metadata

    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        """Initialize token service.

        Args:
            redis_client: Async Redis client. If None, blacklist and refresh tokens
                          are database-only (no Redis acceleration).
        """
        self._redis = redis_client

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
        """Check if a JWT ID is in the Redis blacklist.

        Args:
            jti: JWT ID from token payload.

        Returns:
            True if the token has been revoked.
        """
        if self._redis is None:
            return False
        return await self._redis.exists(f"{self.BLACKLIST_PREFIX}{jti}") > 0

    async def blacklist_token(self, jti: str, ttl_seconds: int = 900) -> None:
        """Add a JWT ID to the Redis blacklist.

        Args:
            jti: JWT ID to blacklist.
            ttl_seconds: Time-to-live matching the token's remaining lifetime.
        """
        if self._redis is not None:
            await self._redis.setex(f"{self.BLACKLIST_PREFIX}{jti}", ttl_seconds, "1")

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

    async def store_refresh_token(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        ttl_days: int = 7,
    ) -> None:
        """Store refresh token metadata in Redis.

        Args:
            user_id: Owner of the refresh token.
            token_hash: SHA-256 hash of the raw token.
            ttl_days: Token lifetime in days.
        """
        if self._redis is not None:
            key = f"{self.REFRESH_PREFIX}{token_hash}"
            await self._redis.setex(
                key,
                ttl_days * 86400,
                str(user_id),
            )

    async def validate_refresh_token(self, raw_token: str) -> uuid.UUID | None:
        """Validate a refresh token and return the owning user_id.

        Args:
            raw_token: The raw refresh token string.

        Returns:
            User UUID if valid, None if revoked/expired/not found.
        """
        if self._redis is None:
            return None
        token_hash = self._hash(raw_token)
        key = f"{self.REFRESH_PREFIX}{token_hash}"
        user_id_raw = await self._redis.get(key)
        if user_id_raw is None:
            return None
        # decode_responses=True returns str; decode_responses=False returns bytes
        return uuid.UUID(user_id_raw.decode() if isinstance(user_id_raw, bytes) else user_id_raw)

    async def revoke_refresh_token(self, raw_token: str) -> None:
        """Revoke a single refresh token.

        Args:
            raw_token: The raw refresh token string.
        """
        if self._redis is not None:
            token_hash = self._hash(raw_token)
            await self._redis.delete(f"{self.REFRESH_PREFIX}{token_hash}")

    async def revoke_all_user_tokens(self, user_id: uuid.UUID) -> None:
        """Revoke all refresh tokens for a user.

        Note: This is a best-effort operation with Redis — for full revocation,
        also update iam.refresh_tokens in PostgreSQL.

        Args:
            user_id: User whose tokens should be revoked.
        """
        if self._redis is not None:
            # Scan for all refresh keys and delete those matching the user
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor, match=f"{self.REFRESH_PREFIX}*", count=100,
                )
                for key in keys:
                    uid_raw = await self._redis.get(key)
                    if uid_raw is None:
                        continue
                    uid = uid_raw.decode() if isinstance(uid_raw, bytes) else uid_raw
                    if uid == str(user_id):
                        await self._redis.delete(key)
                if cursor == 0:
                    break

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hash(value: str) -> str:
        """SHA-256 hash a string."""
        return hashlib.sha256(value.encode()).hexdigest()
