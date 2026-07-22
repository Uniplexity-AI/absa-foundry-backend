"""
Shared Auth Audit — authentication event logging to PostgreSQL.

Writes all auth events (login, logout, token refresh, failed attempts)
to iam.auth_audit for compliance and security monitoring.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import psycopg2
from psycopg2 import pool

from shared.config.settings import settings

logger = logging.getLogger("auth.audit")

# Dedicated connection pool for audit writes (avoids contention with user repo)
_audit_pool: pool.ThreadedConnectionPool | None = None


def _get_pool() -> pool.ThreadedConnectionPool:
    global _audit_pool
    if _audit_pool is None:
        _audit_pool = pool.ThreadedConnectionPool(
            minconn=1, maxconn=5, dsn=settings.database_url_sync,
        )
    return _audit_pool


class AuthAudit:
    """Writes structured auth events to iam.auth_audit."""

    @staticmethod
    async def log(
        event_type: str,
        user_id: UUID | None = None,
        service_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> None:
        """Log an authentication event to PostgreSQL.

        Args:
            event_type: LOGIN_SUCCESS, LOGIN_FAILED, LOGOUT, TOKEN_REFRESH,
                        ACCOUNT_LOCKED, RATE_LIMITED, PASSWORD_POLICY_VIOLATION.
            user_id: User UUID (None for anonymous or service accounts).
            service_id: Service UUID (None for human users).
            ip_address: Client IP address.
            user_agent: Client User-Agent header.
            details: Additional JSON-serializable context.
        """
        # Always log to application logger
        logger.info(
            "AUTH_EVENT type=%s user=%s ip=%s",
            event_type,
            str(user_id)[:8] if user_id else "-",
            ip_address or "-",
        )

        # Write to PostgreSQL (fire-and-forget — don't block on audit failures)
        try:
            _p = _get_pool()
            conn = _p.getconn()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO iam.auth_audit (user_id, service_id, event_type, ip_address, user_agent, details)
                VALUES (%s, %s, %s, %s::INET, %s, %s)
                """,
                (
                    str(user_id) if user_id else None,
                    str(service_id) if service_id else None,
                    event_type,
                    ip_address,
                    (user_agent or "")[:500],
                    json.dumps(details) if details else None,
                ),
            )
            conn.commit()
        except Exception:
            # Audit failure should not break the request
            logger.warning("Failed to write auth audit record (non-critical)", exc_info=True)
        finally:
            try:
                _p.putconn(conn)
            except Exception:
                pass

