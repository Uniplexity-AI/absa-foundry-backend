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
from shared.database.soft_delete import live_customer_filter

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

#: Soft-deleted customers (``customers_clean.is_deleted``) must never surface in
#: a customer-facing read. The rule itself lives in one place
#: (``shared.database.soft_delete``) so it cannot drift between queries — every
#: list/count/aggregate below composes it.
_LIVE_CUSTOMER_FILTER = live_customer_filter("customer_states.customer_id")

FETCH_STATE_SQL = f"""
SELECT customer_id, as_of_date, state, classification_rules,
       health_score, component_scores, computed_at
FROM customer_states
WHERE customer_id = %(customer_id)s
  AND as_of_date = %(as_of_date)s
{_LIVE_CUSTOMER_FILTER}
"""

FETCH_TIMELINE_SQL = f"""
SELECT as_of_date, state
FROM customer_states
WHERE customer_id = %(customer_id)s
{_LIVE_CUSTOMER_FILTER}
ORDER BY as_of_date DESC
LIMIT %(limit)s
"""

PORTFOLIO_SQL = f"""
SELECT
    state,
    COUNT(*) AS count,
    ROUND(COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER(), 0) * 100, 1) AS pct
FROM customer_states
WHERE as_of_date = %(as_of_date)s
{_LIVE_CUSTOMER_FILTER}
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

LIST_ALL_SQL = f"""
SELECT customer_id, as_of_date, state, classification_rules,
       health_score, component_scores, computed_at
FROM customer_states
WHERE as_of_date = %(as_of_date)s
{_LIVE_CUSTOMER_FILTER}
ORDER BY customer_id
LIMIT %(limit)s OFFSET %(offset)s
"""

#: Total rows for the date. LIST_ALL_SQL is capped (le=500) and returns a bare
#: array, so callers have no way to tell "500 of 500" from "500 of 5,000";
#: this is the authoritative denominator for pagination and portfolio totals.
COUNT_STATES_SQL = f"""
SELECT COUNT(*) FROM customer_states WHERE as_of_date = %(as_of_date)s
{_LIVE_CUSTOMER_FILTER}
"""

#: Distinct snapshot dates that already have computed states (newest first).
#: These are the options the UI's "as-of" selector offers; a date with features
#: but no states yet only appears once /states/compute has run for it.
SNAPSHOT_DATES_SQL = f"""
SELECT DISTINCT as_of_date
FROM customer_states
WHERE as_of_date IS NOT NULL
{_LIVE_CUSTOMER_FILTER}
ORDER BY as_of_date DESC
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

    def list_all(self, as_of_date, limit: int = 100, offset: int = 0) -> list[dict]:
        """List all customer states for a given date with pagination."""
        conn = self._connect()
        try:
            cur = conn.cursor(cursor_factory=extras.RealDictCursor)
            cur.execute(LIST_ALL_SQL, {
                "as_of_date": as_of_date,
                "limit": limit,
                "offset": offset,
            })
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def count_states(self, as_of_date) -> int:
        """Total customer states for the date (the real denominator for paging)."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(COUNT_STATES_SQL, {"as_of_date": as_of_date})
            return int(cur.fetchone()[0])
        finally:
            conn.close()

    def list_snapshot_dates(self) -> list[str]:
        """Distinct as_of_date values that have computed states (newest first)."""
        def _query():
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(SNAPSHOT_DATES_SQL)
                return [row[0].isoformat() for row in cur.fetchall() if row[0]]
            finally:
                conn.close()
        return self._retry_db_op(_query, "list_snapshot_dates")

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