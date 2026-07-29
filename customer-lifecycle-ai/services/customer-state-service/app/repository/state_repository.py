"""State Repository — Data access for customer_states table.

Mirrors FeatureRepository exactly:
- psycopg2 (sync) with connection timeouts + TCP keepalives
- Batch upsert via execute_values (ON CONFLICT DO UPDATE)
- Idempotent by design — re-running produces identical results
- Reads from etl_clean (same DB as customer_features)
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone

import psycopg2
from psycopg2 import extras

from shared.config.settings import settings

logger = logging.getLogger("customer_state.repository")

# Retry configuration
_RETRY_MAX = 3
_RETRY_BASE_DELAY = 0.5  # seconds, doubles each retry


# SQL templates — parameterized, no string interpolation
UPSERT_STATES_SQL = """
INSERT INTO customer_states (
    customer_id, as_of_date, state, classification_rules, computed_at
) VALUES %s
ON CONFLICT (customer_id, as_of_date) DO UPDATE SET
    state                  = EXCLUDED.state,
    classification_rules   = EXCLUDED.classification_rules,
    computed_at            = EXCLUDED.computed_at
    -- health_score and component_scores are NOT overwritten —
    -- Layer 2 backfill is preserved across Layer 1 re-runs.
"""

FETCH_STATE_SQL = """
SELECT customer_id, as_of_date, state, classification_rules,
       health_score, component_scores, computed_at
FROM customer_states
WHERE customer_id = %(customer_id)s
  AND as_of_date = %(as_of_date)s
"""

FETCH_TIMELINE_SQL = """
SELECT as_of_date, state
FROM customer_states
WHERE customer_id = %(customer_id)s
ORDER BY as_of_date DESC
LIMIT %(limit)s
"""

PORTFOLIO_SQL = """
SELECT
    state,
    COUNT(*) AS count,
    ROUND(COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER(), 0) * 100, 1) AS pct
FROM customer_states
WHERE as_of_date = %(as_of_date)s
GROUP BY state
ORDER BY COUNT(*) DESC
"""

PREVIOUS_STATE_SQL = """
SELECT DISTINCT ON (customer_id) customer_id, state
FROM customer_states
WHERE customer_id = ANY(%(customer_ids)s)
  AND as_of_date < %(as_of_date)s
ORDER BY customer_id, as_of_date DESC
"""


class StateRepository:
    """Data access for customer_states table.

    Mirrors FeatureRepository: psycopg2 sync, _connect() with timeouts,
    batch upsert via execute_values, ON CONFLICT for idempotency.
    """

    _CONNECT_TIMEOUT = 10
    _retry_max = _RETRY_MAX
    _retry_base_delay = _RETRY_BASE_DELAY

    def __init__(self) -> None:
        self._conn_str = settings.database_target_url_sync  # etl_clean

    def _connect(self) -> psycopg2.extensions.connection:
        """Mirrors FeatureRepository._connect() — timeouts + keepalives."""
        return psycopg2.connect(
            self._conn_str,
            connect_timeout=self._CONNECT_TIMEOUT,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3,
        )

    def _retry_db_op(self, op, op_name: str = "db_op"):
        """Retry a database operation with exponential backoff.

        Args:
            op: Callable that performs the DB operation.
            op_name: Human-readable name for logging.

        Returns:
            Result of op().

        Raises:
            psycopg2.OperationalError after exhausting retries.
        """
        last_err = None
        for attempt in range(1, self._retry_max + 1):
            try:
                return op()
            except psycopg2.OperationalError as e:
                last_err = e
                if attempt < self._retry_max:
                    delay = self._retry_base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "DB %s failed (attempt %d/%d), retrying in %.1fs: %s",
                        op_name, attempt, self._retry_max, delay, e,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "DB %s failed after %d retries: %s",
                        op_name, self._retry_max, e,
                    )
        raise last_err  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert_batch(self, states: list[dict], as_of_date: date) -> int:
        """Batch upsert customer states. Idempotent via ON CONFLICT.

        Args:
            states: List of dicts with keys: customer_id, as_of_date, state,
                    classification_rules.
            as_of_date: Date for all states in this batch.

        Returns:
            Number of rows upserted.
        """
        if not states:
            return 0

        conn = self._connect()
        now = datetime.now(timezone.utc)
        values = [
            (
                s["customer_id"],
                as_of_date,
                s["state"],
                psycopg2.extras.Json(s.get("classification_rules", {})),
                now,
            )
            for s in states
        ]
        try:
            cur = conn.cursor()
            extras.execute_values(
                cur,
                UPSERT_STATES_SQL,
                values,
                template="(%s, %s, %s, %s, %s)",
                page_size=5000,
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_state(self, customer_id: str, as_of_date: date) -> dict | None:
        """Get a single customer state snapshot."""
        def _query():
            conn = self._connect()
            try:
                cur = conn.cursor(cursor_factory=extras.RealDictCursor)
                cur.execute(FETCH_STATE_SQL, {
                    "customer_id": customer_id,
                    "as_of_date": as_of_date,
                })
                row = cur.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
        return self._retry_db_op(_query, f"get_state({customer_id})")

    def get_timeline(self, customer_id: str, limit: int = 50) -> list[dict]:
        """Get full state history for a customer (most recent first)."""
        conn = self._connect()
        try:
            cur = conn.cursor(cursor_factory=extras.RealDictCursor)
            cur.execute(FETCH_TIMELINE_SQL, {
                "customer_id": customer_id,
                "limit": limit,
            })
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_portfolio_summary(
        self, as_of_date: date, branch_code: str | None = None
    ) -> dict:
        """Aggregate state counts for a given date."""
        conn = self._connect()
        try:
            cur = conn.cursor(cursor_factory=extras.RealDictCursor)
            cur.execute(PORTFOLIO_SQL, {"as_of_date": as_of_date})
            rows = [dict(r) for r in cur.fetchall()]
            by_state = {
                r["state"]: {"count": r["count"], "pct": float(r["pct"])}
                for r in rows
            }
            total = sum(r["count"] for r in rows)
            return {
                "as_of_date": as_of_date,
                "branch_code": branch_code,
                "total_customers": total,
                "by_state": by_state,
            }
        finally:
            conn.close()

    def get_previous_states(
        self, customer_ids: list[str], as_of_date: date
    ) -> dict[str, str]:
        """Get the most recent state before as_of_date for a batch of customers.

        Returns:
            Dict of customer_id → previous_state (or None if first snapshot).
        """
        if not customer_ids:
            return {}
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(PREVIOUS_STATE_SQL, {
                "customer_ids": customer_ids,
                "as_of_date": as_of_date,
            })
            return {row[0]: row[1] for row in cur.fetchall()}
        finally:
            conn.close()

    def count_customers(self, as_of_date: date) -> int:
        """Count customers with features for a given date."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM customer_features WHERE as_of_date = %(d)s",
                {"d": as_of_date},
            )
            return cur.fetchone()[0]
        finally:
            conn.close()