"""Prediction Repository — Data access for customer_features + customer_states.

Mirrors FeatureRepository + StateRepository exactly:
- psycopg2 (sync) with connection timeouts + TCP keepalives
- Batch backfill via execute_values
- Reads customer_features (56 cols) and customer_states
- 3× exponential retry on OperationalError
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone

import psycopg2
from psycopg2 import extras

from shared.config.settings import settings

logger = logging.getLogger("prediction.repository")

# Retry configuration
_RETRY_MAX = 3
_RETRY_BASE_DELAY = 0.5  # seconds, doubles each retry

# ── SQL Templates ──────────────────────────────────────────────────
# Table/column names are resolved from shared config via str.format().
# {name} placeholders are filled at init time; %(...)s are psycopg2 params.

_SQL_TEMPLATES = {
    "load_features": """
SELECT *
FROM {features_table}
WHERE {as_of_col} = %(as_of_date)s
ORDER BY {cust_col}
""",
    "clv_percentiles": """
SELECT
    {cust_col},
    PERCENT_RANK() OVER (ORDER BY {total_amount_col}) AS clv_percentile
FROM {features_table}
WHERE {as_of_col} = %(as_of_date)s
""",
    "fetch_state": """
SELECT state
FROM {states_table}
WHERE {cust_col} = %(customer_id)s
  AND {as_of_col} = %(as_of_date)s
""",
    "backfill_health": """
UPDATE {states_table} cs
SET
    health_score     = pred.health_score,
    component_scores = pred.component_scores::jsonb,
    computed_at      = NOW()
FROM (
    VALUES %s
) AS pred({cust_col}, {as_of_col}, health_score, component_scores)
WHERE cs.{cust_col} = pred.{cust_col}::text
  AND cs.{as_of_col} = pred.{as_of_col}::date
""",
}


class PredictionRepository:
    """Data access for customer_features + customer_states.

    Mirrors FeatureRepository + StateRepository:
    - psycopg2 sync with _connect() timeouts + keepalives
    - _retry_db_op() with 3× exponential backoff
    - Batch backfill via execute_values

    Table/column names resolved from shared config at init time.
    """

    _CONNECT_TIMEOUT = 10
    _retry_max = _RETRY_MAX
    _retry_base_delay = _RETRY_BASE_DELAY

    def __init__(self) -> None:
        self._conn_str = settings.database_target_url_sync  # etl_clean

        # Resolve schema mapping from shared config
        ft = settings.table_customer_features
        st = settings.table_customer_states
        cc = settings.col_customer_id
        ac = settings.col_as_of_date
        ta = settings.col_total_amount_90d

        # Build SQL from templates
        self._load_features_sql = _SQL_TEMPLATES["load_features"].format(
            features_table=ft, as_of_col=ac, cust_col=cc,
        )
        self._clv_percentiles_sql = _SQL_TEMPLATES["clv_percentiles"].format(
            features_table=ft, as_of_col=ac, cust_col=cc, total_amount_col=ta,
        )
        self._fetch_state_sql = _SQL_TEMPLATES["fetch_state"].format(
            states_table=st, cust_col=cc, as_of_col=ac,
        )
        self._backfill_health_sql = _SQL_TEMPLATES["backfill_health"].format(
            states_table=st, cust_col=cc, as_of_col=ac,
        )

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
    # Read — Features
    # ------------------------------------------------------------------

    def load_features(self, as_of_date: date) -> list[dict]:
        """Read all 56 feature columns for a date from customer_features.

        Returns list of dicts with customer_id + all feature columns.
        The full 56-column dict is passed AS-IS to ChurnPredictor —
        the predictor's _dict_to_vector() gatekeeper extracts only
        training_features, leaving leakage columns behind.
        """
        def _query():
            conn = self._connect()
            try:
                cur = conn.cursor(cursor_factory=extras.RealDictCursor)
                cur.execute(self._load_features_sql, {"as_of_date": as_of_date})
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()

        return self._retry_db_op(_query, f"load_features({as_of_date})")

    def load_clv_percentiles(self, as_of_date: date) -> dict[str, float]:
        """PERCENT_RANK() of total_amount_90d across all customers.

        Returns dict of customer_id → percentile [0, 1].
        """
        def _query():
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(self._clv_percentiles_sql, {"as_of_date": as_of_date})
                return {row[0]: float(row[1]) for row in cur.fetchall()}
            finally:
                conn.close()

        return self._retry_db_op(_query, f"load_clv_percentiles({as_of_date})")

    # ------------------------------------------------------------------
    # Read — State
    # ------------------------------------------------------------------

    def load_state(self, customer_id: str, as_of_date: date) -> str | None:
        """Get customer state from customer_states."""
        def _query():
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(self._fetch_state_sql, {
                    "customer_id": customer_id,
                    "as_of_date": as_of_date,
                })
                row = cur.fetchone()
                return row[0] if row else None
            finally:
                conn.close()

        return self._retry_db_op(_query, f"load_state({customer_id})")

    # ------------------------------------------------------------------
    # Write — Health Score Backfill
    # ------------------------------------------------------------------

    def backfill_health_scores(
        self, scores: list[dict], as_of_date: date
    ) -> int:
        """Batch UPDATE customer_states SET health_score, component_scores.

        Uses psycopg2.extras.execute_values for batch performance.
        Returns number of rows updated.

        Args:
            scores: list of {customer_id, health_score, component_scores}
            as_of_date: date for all scores in this batch
        """
        if not scores:
            return 0

        conn = self._connect()
        now = datetime.now(timezone.utc)
        values = [
            (
                s["customer_id"],
                as_of_date,
                s["health_score"],
                psycopg2.extras.Json(s["component_scores"]),
            )
            for s in scores
        ]
        try:
            cur = conn.cursor()
            extras.execute_values(
                cur,
                self._backfill_health_sql,
                values,
                template="(%s, %s, %s, %s)",
                page_size=1000,
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()
