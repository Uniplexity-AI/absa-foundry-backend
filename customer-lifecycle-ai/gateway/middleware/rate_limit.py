"""
Gateway Rate Limiting Middleware — Redis-based sliding window rate limiter.

Configurable per-route limits. Uses Redis sorted sets for accurate
sliding window counters. Falls back to in-memory if Redis is unavailable.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import redis.asyncio as aioredis
from fastapi import Request, HTTPException, status

logger = logging.getLogger("gateway.rate_limit")


@dataclass
class RateLimitRule:
    """A rate limit rule for a specific route pattern."""
    method: str
    path: str
    max_requests: int
    window_seconds: int


# Default rate limit rules
DEFAULT_RULES: list[RateLimitRule] = [
    RateLimitRule("POST", "/auth/login",    max_requests=5,  window_seconds=900),   # 5 attempts / 15 min
    RateLimitRule("POST", "/auth/refresh",  max_requests=30, window_seconds=60),    # 30 refreshes / minute
    RateLimitRule("*",    "/admin/*",       max_requests=60, window_seconds=60),    # 60 admin calls / minute
]

# In-memory fallback when Redis is unavailable
_MEMORY_BUCKETS: dict[str, list[float]] = {}


class RateLimiter:
    """Redis-backed sliding window rate limiter with in-memory fallback."""

    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        self._redis = redis_client
        self._rules = DEFAULT_RULES

    async def check(self, request: Request) -> None:
        """Check if the request exceeds rate limits.

        Args:
            request: Incoming FastAPI request.

        Raises:
            HTTPException 429: Rate limit exceeded.
        """
        # Find matching rule
        rule = self._match_rule(request.method, request.url.path)
        if rule is None:
            return

        key = self._build_key(request, rule)
        allowed = await self._is_allowed(key, rule.max_requests, rule.window_seconds)

        if not allowed:
            logger.warning(
                "Rate limit exceeded: %s %s (ip=%s, limit=%d/%ds)",
                request.method, request.url.path,
                request.client.host if request.client else "unknown",
                rule.max_requests, rule.window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "retry_after_seconds": rule.window_seconds,
                },
            )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _match_rule(self, method: str, path: str) -> RateLimitRule | None:
        """Find the first matching rate limit rule."""
        for rule in self._rules:
            # Method match
            if rule.method != "*" and rule.method.upper() != method.upper():
                continue
            # Path match — supports wildcard: /admin/* matches /admin/users
            if rule.path.endswith("/*"):
                prefix = rule.path[:-2]
                if path.startswith(prefix):
                    return rule
            elif rule.path == path:
                return rule
        return None

    def _build_key(self, request: Request, rule: RateLimitRule) -> str:
        """Build a unique Redis key for this client + rule."""
        ip = request.client.host if request.client else "unknown"
        return f"ratelimit:{rule.method}:{rule.path}:{ip}"

    async def _is_allowed(self, key: str, max_req: int, window: int) -> bool:
        """Check if the request is within the rate limit window."""
        if self._redis is not None:
            return await self._redis_check(key, max_req, window)
        return self._memory_check(key, max_req, window)

    async def _redis_check(self, key: str, max_req: int, window: int) -> bool:
        """Redis sorted set sliding window check."""
        now = time.time()
        window_start = now - window

        # Remove expired entries
        await self._redis.zremrangebyscore(key, 0, window_start)

        # Count current window
        count = await self._redis.zcard(key)
        if count >= max_req:
            return False

        # Add current request
        await self._redis.zadd(key, {str(now): now})
        await self._redis.expire(key, window)
        return True

    def _memory_check(self, key: str, max_req: int, window: int) -> bool:
        """In-memory fallback using a simple list."""
        now = time.time()
        window_start = now - window

        bucket = _MEMORY_BUCKETS.setdefault(key, [])
        # Prune old entries
        bucket[:] = [t for t in bucket if t > window_start]

        if len(bucket) >= max_req:
            return False

        bucket.append(now)
        return True


# Singleton
rate_limiter = RateLimiter()
