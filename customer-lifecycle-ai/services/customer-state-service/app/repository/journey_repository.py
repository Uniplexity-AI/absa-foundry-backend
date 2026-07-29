"""Journey Repository — Data access for state_transitions table.

Same pattern as StateRepository: psycopg2 sync, _connect() with timeouts.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone

import psycopg2
from psycopg2 import extras

from shared.config.settings import settings

logger = logging.getLogger("customer_state.journey_repository")

_RETRY_MAX = 3
_RETRY_BASE_DELAY = 0.5


INSERT_TRANSITIONS_SQL = """
INSERT INTO state_transitions (
    customer_id, from_state, to_state, transition_date,
    days_in_previous_state, trigger_reason, feature_snapshot, computed_at
) VALUES %s
"""

FETCH_TRANSITIONS_SQL = """
SELECT customer_id, from_state, to_state, transition_date,
       days_in_previous_state, trigger_reason, feature_snapshot
FROM state_transitions
WHERE customer_id = %(customer_id)s
ORDER BY transition_date DESC
"""

TRANSITION_MATRIX_SQL = """
SELECT from_state, to_state, COUNT(*) AS transition_count
FROM state_transitions
WHERE transition_date > (%(as_of_date)s::date - INTERVAL '%(window_days)s days')
  AND transition_date <= %(as_of_date)s::date
GROUP BY from_state, to_state
"""


class JourneyRepository:
    """Data access for state_transitions table. Same pattern as StateRepository."""

    _CONNECT_TIMEOUT = 10
    _retry_max = _RETRY_MAX
    _retry_base_delay = _RETRY_BASE_DELAY

    def __init__(self) -> None:
        self._conn_str = settings.database_target_url_sync

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
        """Retry a database operation with exponential backoff."""
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
                    logger.error("DB %s failed after %d retries: %s", op_name, self._retry_max, e)
        raise last_err  # type: ignore[misc]

    def insert_transitions(self, transitions: list[dict]) -> int:
        """Batch insert state transitions."""
        if not transitions:
            return 0
        conn = self._connect()
        now = datetime.now(timezone.utc)
        values = [
            (
                t["customer_id"],
                t["from_state"],
                t["to_state"],
                t["transition_date"],
                t.get("days_in_previous_state"),
                t.get("trigger_reason"),
                psycopg2.extras.Json(t.get("feature_snapshot", {})),
                now,
            )
            for t in transitions
        ]
        try:
            cur = conn.cursor()
            extras.execute_values(
                cur,
                INSERT_TRANSITIONS_SQL,
                values,
                template="(%s, %s, %s, %s, %s, %s, %s, %s)",
                page_size=5000,
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def get_transitions(self, customer_id: str) -> list[dict]:
        """Get all state transitions for a customer (most recent first)."""
        conn = self._connect()
        try:
            cur = conn.cursor(cursor_factory=extras.RealDictCursor)
            cur.execute(FETCH_TRANSITIONS_SQL, {"customer_id": customer_id})
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_transition_matrix_data(
        self, as_of_date: date, window_days: int = 180
    ) -> list[dict]:
        """Aggregated (from_state, to_state, count) for Markov matrix."""
        conn = self._connect()
        try:
            cur = conn.cursor(cursor_factory=extras.RealDictCursor)
            # window_days is sanitized — only int, validated by caller
            sql = TRANSITION_MATRIX_SQL.replace(
                "%(window_days)s", str(window_days)
            )
            cur.execute(sql, {"as_of_date": as_of_date})
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()