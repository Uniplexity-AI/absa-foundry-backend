"""
Shared Auth User Repository — DB operations for users, roles, and refresh tokens.

Uses psycopg2 (sync) for now — consistent with run_etl.py.
Will be upgraded to SQLAlchemy async in Phase 2.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg2
from psycopg2 import pool

from shared.auth.models import UserContext
from shared.config.settings import settings

logger = logging.getLogger("auth.repository")


class UserRepository:
    """Syncs users from LDAP to iam.users and resolves roles."""

    def __init__(self) -> None:
        """Initialize with a connection pool to the source database."""
        self._pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=settings.database_url_sync,
        )

    # ------------------------------------------------------------------
    # User sync (LDAP → DB)
    # ------------------------------------------------------------------

    def sync_user(
        self,
        username: str,
        email: str,
        display_name: str,
        dn: str,
        department: str | None = None,
    ) -> UserContext:
        """Upsert a user from LDAP and resolve their roles.

        If the user exists, updates their profile. If new, creates with no roles
        (admin must assign roles before they can access anything).

        Args:
            username: AD sAMAccountName.
            email: User's email from AD.
            display_name: User's display name from AD.
            dn: LDAP distinguished name.
            department: Optional department from AD.

        Returns:
            UserContext with user_id and resolved roles.
        """
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()

            # Upsert user
            cur.execute(
                """
                INSERT INTO iam.users (user_id, username, email, display_name, dn, department, last_login_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (username) DO UPDATE SET
                    email = EXCLUDED.email,
                    display_name = EXCLUDED.display_name,
                    dn = EXCLUDED.dn,
                    department = COALESCE(EXCLUDED.department, iam.users.department),
                    last_login_at = EXCLUDED.last_login_at,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING user_id, branch_code, is_active
                """,
                (str(uuid4()), username, email, display_name, dn, department,
                 datetime.now(timezone.utc)),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(f"Failed to upsert user '{username}'")

            user_id, branch_code, is_active = row

            if not is_active:
                raise ValueError(f"User '{username}' is deactivated")

            # Resolve roles
            cur.execute(
                """
                SELECT r.role_name
                FROM iam.user_roles ur
                JOIN iam.roles r ON r.role_id = ur.role_id
                WHERE ur.user_id = %s
                ORDER BY r.role_name
                """,
                (str(user_id),),
            )
            roles = [row[0] for row in cur.fetchall()]

            conn.commit()

            return UserContext(
                user_id=user_id,
                username=username,
                display_name=display_name,
                email=email,
                roles=roles,
                branch_code=branch_code,
            )

        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    # ------------------------------------------------------------------
    # Role queries
    # ------------------------------------------------------------------

    def get_roles(self) -> list[dict]:
        """List all roles."""
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT role_id, role_name, description FROM iam.roles ORDER BY role_id")
            return [
                {"role_id": r[0], "role_name": r[1], "description": r[2]}
                for r in cur.fetchall()
            ]
        finally:
            self._pool.putconn(conn)

    # ------------------------------------------------------------------
    # Refresh token persistence (PostgreSQL)
    # ------------------------------------------------------------------

    def store_refresh_token(
        self,
        user_id: UUID,
        token_hash: str,
        ip_address: str | None = None,
        ttl_days: int = 7,
    ) -> None:
        """Persist a refresh token hash to iam.refresh_tokens."""
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO iam.refresh_tokens (user_id, token_hash, ip_address, expires_at)
                VALUES (%s, %s, %s::INET, %s)
                """,
                (
                    str(user_id),
                    token_hash,
                    ip_address,
                    datetime.now(timezone.utc) + timedelta(days=ttl_days),
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def validate_refresh_token(self, token_hash: str) -> UUID | None:
        """Check if a refresh token is valid and return the user_id."""
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT user_id FROM iam.refresh_tokens
                WHERE token_hash = %s
                  AND revoked_at IS NULL
                  AND expires_at > CURRENT_TIMESTAMP
                """,
                (token_hash,),
            )
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            self._pool.putconn(conn)

    def revoke_refresh_token(self, token_hash: str) -> None:
        """Revoke a single refresh token."""
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE iam.refresh_tokens SET revoked_at = CURRENT_TIMESTAMP WHERE token_hash = %s",
                (token_hash,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            self._pool.putconn(conn)

    def revoke_all_user_tokens(self, user_id: UUID) -> None:
        """Revoke all refresh tokens for a user."""
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE iam.refresh_tokens SET revoked_at = CURRENT_TIMESTAMP WHERE user_id = %s AND revoked_at IS NULL",
                (str(user_id),),
            )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            self._pool.putconn(conn)

    # ------------------------------------------------------------------
    # API Key operations
    # ------------------------------------------------------------------

    def create_service_account(self, service_name: str, description: str = "") -> str:
        """Create or get a service account. Returns the service_id."""
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO iam.service_accounts (service_name, description)
                VALUES (%s, %s)
                ON CONFLICT (service_name) DO UPDATE SET description = EXCLUDED.description
                RETURNING service_id
                """,
                (service_name, description),
            )
            row = cur.fetchone()
            conn.commit()
            if row is None:
                raise RuntimeError(f"Failed to create service account '{service_name}'")
            return str(row[0])
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def store_api_key(
        self,
        service_name: str,
        key_hash: str,
        key_prefix: str,
        key_name: str,
        scopes: list[str],
        expires_in_days: int | None = None,
    ) -> dict:
        """Store a new API key in iam.api_keys. Creates the service account if needed.

        Returns dict with key_id, service_id, service_name.
        """
        service_id = self.create_service_account(service_name)

        expires_at = None
        if expires_in_days:
            from datetime import timedelta
            expires_at = f"CURRENT_TIMESTAMP + INTERVAL '{expires_in_days} days'"

        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                INSERT INTO iam.api_keys (service_id, api_key_hash, key_prefix, name, scopes, expires_at)
                VALUES (%s, %s, %s, %s, %s, {expires_at or 'NULL'})
                RETURNING key_id
                """,
                (service_id, key_hash, key_prefix, key_name, scopes),
            )
            row = cur.fetchone()
            conn.commit()
            return {
                "key_id": row[0],
                "service_id": service_id,
                "service_name": service_name,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def validate_api_key(self, key_hash: str) -> dict | None:
        """Validate an API key and return service info.

        Returns dict with service_id, service_name, scopes, or None.
        """
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT k.key_id, s.service_id, s.service_name, k.scopes
                FROM iam.api_keys k
                JOIN iam.service_accounts s ON s.service_id = k.service_id
                WHERE k.api_key_hash = %s
                  AND k.is_active = TRUE
                  AND s.is_active = TRUE
                  AND (k.expires_at IS NULL OR k.expires_at > CURRENT_TIMESTAMP)
                """,
                (key_hash,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            # Update last_used_at
            cur.execute(
                "UPDATE iam.api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE key_id = %s",
                (row[0],),
            )
            conn.commit()

            return {
                "key_id": row[0],
                "service_id": row[1],
                "service_name": row[2],
                "scopes": row[3] if row[3] else [],
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def list_api_keys(self) -> list[dict]:
        """List all API keys (without raw key/hash values)."""
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT k.key_id, k.key_prefix, s.service_name, k.name, k.scopes,
                       k.last_used_at, k.expires_at, k.is_active, k.created_at
                FROM iam.api_keys k
                JOIN iam.service_accounts s ON s.service_id = k.service_id
                ORDER BY k.created_at DESC
                """
            )
            columns = [d[0] for d in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
        finally:
            self._pool.putconn(conn)

    def revoke_api_key(self, key_id: str) -> bool:
        """Revoke (soft-delete) an API key. Returns True if found."""
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE iam.api_keys SET is_active = FALSE WHERE key_id = %s",
                (key_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    # ------------------------------------------------------------------
    # User queries (for admin routes)
    # ------------------------------------------------------------------

    def list_users(self) -> list[dict]:
        """List all users with roles."""
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT u.user_id, u.username, u.email, u.display_name,
                       u.department, u.branch_code, u.is_active,
                       u.last_login_at, u.created_at,
                       COALESCE(array_agg(r.role_name) FILTER (WHERE r.role_name IS NOT NULL), '{}') AS roles
                FROM iam.users u
                LEFT JOIN iam.user_roles ur ON ur.user_id = u.user_id
                LEFT JOIN iam.roles r ON r.role_id = ur.role_id
                GROUP BY u.user_id
                ORDER BY u.username
                """
            )
            columns = [d[0] for d in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
        finally:
            self._pool.putconn(conn)

    def assign_role(self, username: str, role_name: str) -> bool:
        """Assign a role to a user. Returns True if newly assigned."""
        conn = self._pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO iam.user_roles (user_id, role_id)
                SELECT u.user_id, r.role_id
                FROM iam.users u, iam.roles r
                WHERE u.username = %s AND r.role_name = %s
                ON CONFLICT (user_id, role_id) DO NOTHING
                """,
                (username, role_name),
            )
            conn.commit()
            return cur.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)
