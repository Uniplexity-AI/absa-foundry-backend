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
    PERCENT_RANK() OVER (ORDER BY COALESCE({total_amount_col}, 0)) AS clv_percentile
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

    def drift_feature_windows(
        self, columns: list[str], baseline_date: date | None = None,
    ) -> list[dict]:
        """Raw values per feature for the baseline and latest snapshots.

        baseline_date defaults to the second-latest snapshot when the
        registry's training dates are unavailable. Caller computes PSI.
        Columns are validated as identifiers before interpolation.
        """
        for col in columns:
            if not col.replace("_", "").isalnum():
                raise ValueError(f"invalid drift column: {col!r}")
        col_sql = ", ".join(f'"{c}"' for c in columns)

        def _query():
            conn = self._connect()
            try:
                cur = conn.cursor()
                if baseline_date is None:
                    cur.execute(
                        "SELECT DISTINCT as_of_date FROM customer_features "
                        "ORDER BY as_of_date DESC LIMIT 2"
                    )
                    dates = [r[0] for r in cur.fetchall()]
                    base = dates[1] if len(dates) > 1 else dates[0]
                else:
                    base = baseline_date
                cur.execute("SELECT MAX(as_of_date) FROM customer_features")
                current = cur.fetchone()[0]
                if base is None or current is None or base == current:
                    return [
                        {"name": c, "baseline_mean": 0.0, "current_mean": 0.0, "psi": 0.0}
                        for c in columns
                    ]
                out = []
                for col in columns:
                    cur.execute(
                        f'SELECT ARRAY_AGG("{col}") FROM customer_features '
                        f'WHERE as_of_date = %(b)s AND "{col}" IS NOT NULL',
                        {"b": base},
                    )
                    baseline_vals = [float(v) for v in (cur.fetchone()[0] or []) if v is not None]
                    cur.execute(
                        f'SELECT ARRAY_AGG("{col}") FROM customer_features '
                        f'WHERE as_of_date = %(c)s AND "{col}" IS NOT NULL',
                        {"c": current},
                    )
                    current_vals = [float(v) for v in (cur.fetchone()[0] or []) if v is not None]
                    out.append({
                        "name": col,
                        "baseline_mean": (sum(baseline_vals) / len(baseline_vals)) if baseline_vals else 0.0,
                        "current_mean": (sum(current_vals) / len(current_vals)) if current_vals else 0.0,
                        "baseline_vals": baseline_vals,
                        "current_vals": current_vals,
                    })
                return out
            finally:
                conn.close()
        return self._retry_db_op(_query, "drift_feature_windows")

    def latest_feature_date(self) -> date | None:
        """Most recent as_of_date present in customer_features (None if empty)."""
        def _query():
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute("SELECT MAX(as_of_date) FROM customer_features")
                return cur.fetchone()[0]
            finally:
                conn.close()

        return self._retry_db_op(_query, "latest_feature_date()")

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

    # ------------------------------------------------------------------
    # Write — prediction telemetry (best-effort)
    # ------------------------------------------------------------------

    def log_prediction(
        self,
        customer_id: str,
        as_of_date: date,
        model_id: str,
        model_version: str | None,
        churn_probability: float,
        predicted_class: str,
        latency_ms: float | None,
    ) -> None:
        """Insert one prediction_log row. Never raises — telemetry must not
        fail the scoring request."""
        try:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO prediction_log
                      (customer_id, as_of_date, model_id, model_version,
                       churn_probability, predicted_class, latency_ms)
                    VALUES (%(c)s, %(d)s, %(m)s, %(v)s, %(p)s, %(cl)s, %(l)s)
                    """,
                    {
                        "c": customer_id, "d": as_of_date, "m": model_id,
                        "v": model_version, "p": churn_probability,
                        "cl": predicted_class, "l": latency_ms,
                    },
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001 — deliberate best-effort
            logger.warning("log_prediction failed for %s: %s", customer_id, e)

    # ------------------------------------------------------------------
    # Read — monitoring (real telemetry)
    # ------------------------------------------------------------------

    def recent_predictions(self, limit: int = 50) -> list[dict]:
        def _query():
            conn = self._connect()
            try:
                cur = conn.cursor(cursor_factory=extras.RealDictCursor)
                cur.execute(
                    """
                    SELECT id, customer_id, as_of_date, model_id, churn_probability,
                           predicted_class, latency_ms, created_at
                    FROM prediction_log
                    ORDER BY created_at DESC
                    LIMIT %(lim)s
                    """,
                    {"lim": limit},
                )
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()
        return self._retry_db_op(_query, "recent_predictions")

    def total_predictions(self) -> int:
        def _query():
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM prediction_log")
                return int(cur.fetchone()[0])
            finally:
                conn.close()
        return self._retry_db_op(_query, "total_predictions")

    def realized_outcomes(self, horizon_days: int = 90) -> list[dict]:
        """Join logged predictions with later CHURNED transitions.

        A prediction realizes as churned when the customer transitions to
        CHURNED within horizon_days after the prediction's as_of_date.
        Realized labels power the true confusion matrix / rolling AUC.
        """
        def _query():
            conn = self._connect()
            try:
                cur = conn.cursor(cursor_factory=extras.RealDictCursor)
                cur.execute(
                    """
                    SELECT p.customer_id,
                           p.as_of_date,
                           p.churn_probability,
                           p.predicted_class,
                           COALESCE(MAX((t.transition_date <= p.as_of_date + %(h)s::int)::int), 0)
                               AS churned
                    FROM prediction_log p
                    LEFT JOIN state_transitions t
                      ON t.customer_id = p.customer_id
                     AND t.to_state = 'CHURNED'
                     AND t.transition_date > p.as_of_date
                     AND t.transition_date <= p.as_of_date + %(h)s::int
                    GROUP BY p.customer_id, p.as_of_date, p.churn_probability,
                             p.predicted_class
                    HAVING COUNT(t.id) >= 0
                    """,
                    {"h": horizon_days},
                )
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()
        return self._retry_db_op(_query, "realized_outcomes")
