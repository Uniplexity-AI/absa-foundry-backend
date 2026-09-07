"""Pilot Action Repository — persistence for frontend action buttons.

The pilot backend has read endpoints for recommendations/intelligence but no
gateway write path for the frontend action buttons (RM assignment, campaign
enrolment, alert ack, NBA override, action-plan/action recording). This repo
gives those clicks a real, shared home in `etl_clean`:

  - pilot_action_log      — append-only audit of every intervention click
  - pilot_customer_state  — latest per-customer mutable state (rm,
                            enrolled campaigns, acked alerts, override)

Connection style mirrors IntelligenceRepository / PredictionRepository:
psycopg2 (sync) with connect timeouts + TCP keepalives, retry on
OperationalError. Reads/writes the same target DB the rest of the platform
uses (POSTGRES_TARGET_*).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime

import psycopg2
from psycopg2 import extras

from shared.config.settings import settings

logger = logging.getLogger("decision.action_repo")

_RETRY_MAX = 3
_RETRY_BASE_DELAY = 0.5
_CONNECT_TIMEOUT = 5


class PilotActionRepository:
    """Read/write for the pilot action-log + per-customer state tables."""

    def __init__(self) -> None:
        self._conn_str = (
            f"host={settings.postgres_target_host} "
            f"port={settings.postgres_target_port} "
            f"dbname={settings.postgres_target_db} "
            f"user={settings.postgres_target_user} "
            f"password={settings.postgres_target_password}"
        )

    def _connect(self):
        return psycopg2.connect(
            self._conn_str,
            connect_timeout=_CONNECT_TIMEOUT,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3,
        )

    def _retry(self, op, name: str):
        last_err = None
        for attempt in range(1, _RETRY_MAX + 1):
            try:
                return op()
            except psycopg2.OperationalError as e:
                last_err = e
                if attempt < _RETRY_MAX:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning("DB %s failed (%d/%d), retry %0.1fs: %s",
                                   name, attempt, _RETRY_MAX, delay, e)
                    time.sleep(delay)
        raise last_err

    # ------------------------------------------------------------------
    # Action log (append-only)
    # ------------------------------------------------------------------

    def insert_action(
        self,
        customer_id: str,
        action_type: str,
        detail: str | None,
        meta: dict | None,
        actor: str | None,
    ) -> int:
        """Insert one action-log row. Returns its id."""

        def _q():
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO pilot_action_log
                        (customer_id, action_type, detail, meta, actor)
                    VALUES (%(c)s, %(t)s, %(d)s, %(m)s::jsonb, %(a)s)
                    RETURNING id
                    """,
                    {
                        "c": customer_id,
                        "t": action_type,
                        "d": detail,
                        "m": json.dumps(meta if meta is not None else {}),
                        "a": actor,
                    },
                )
                row = cur.fetchone()
                conn.commit()
                return row[0] if row else 0
            finally:
                conn.close()

        return self._retry(_q, "insert_action")

    def list_actions(self, customer_id: str | None = None, limit: int = 100) -> list[dict]:
        """Return recent action-log rows (optional per-customer filter)."""

        def _q():
            conn = self._connect()
            try:
                cur = conn.cursor(cursor_factory=extras.RealDictCursor)
                if customer_id:
                    cur.execute(
                        """
                        SELECT id, customer_id, action_type, detail, meta, actor, created_at
                        FROM pilot_action_log
                        WHERE customer_id = %(c)s
                        ORDER BY created_at DESC
                        LIMIT %(limit)s
                        """,
                        {"c": customer_id, "limit": limit},
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, customer_id, action_type, detail, meta, actor, created_at
                        FROM pilot_action_log
                        ORDER BY created_at DESC
                        LIMIT %(limit)s
                        """,
                        {"limit": limit},
                    )
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()

        return self._retry(_q, "list_actions")

    # ------------------------------------------------------------------
    # Per-customer mutable state (upsert by customer_id)
    # ------------------------------------------------------------------

    def get_state(self, customer_id: str) -> dict:
        """Return the JSONB state blob for a customer ({} if absent)."""

        def _q():
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT state FROM pilot_customer_state WHERE customer_id = %(c)s",
                    {"c": customer_id},
                )
                row = cur.fetchone()
                return row[0] if row else {}
            finally:
                conn.close()

        return self._retry(_q, "get_state")

    def upsert_state(self, customer_id: str, patch: dict) -> dict:
        """Merge `patch` into a customer's JSONB state and return merged state."""

        def _q():
            conn = self._connect()
            try:
                cur = conn.cursor()
                # Merge JSONB: existing keys are preserved unless overwritten by patch.
                cur.execute(
                    """
                    INSERT INTO pilot_customer_state (customer_id, state, updated_at)
                    VALUES (%(c)s, %(m)s::jsonb, CURRENT_TIMESTAMP)
                    ON CONFLICT (customer_id) DO UPDATE SET
                        state      = pilot_customer_state.state || EXCLUDED.state,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING state
                    """,
                    {"c": customer_id, "m": json.dumps(patch)},
                )
                merged = cur.fetchone()[0]
                conn.commit()
                return merged
            finally:
                conn.close()

        return self._retry(_q, "upsert_state")
