"""Intelligence Aggregation Repository — direct reads from the shared etl_clean DB.

The Decision Intelligence Service owns portfolio-level aggregation, so it
reads the shared tables (customer_features, customer_states,
state_transitions, decision_outcomes) directly — the same cross-service
table precedent the Prediction Service already sets (it reads
customer_features + customer_states).

Connection style mirrors PredictionRepository: psycopg2 sync with
connect timeouts + TCP keepalives, retry on OperationalError.
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import date

import psycopg2
from psycopg2 import extras

from shared.config.settings import settings

logger = logging.getLogger("decision.intelligence_repo")

_RETRY_MAX = 3
_RETRY_BASE_DELAY = 0.5
_CONNECT_TIMEOUT = 5

# AUM source column: the pilot DB has no balance/AUM field, so we proxy
# with total_amount_90d. Point INTEL_AUM_COLUMN at the real column when
# the production DB provides one — no code change required.
_AUM_COLUMN = os.getenv("INTEL_AUM_COLUMN", "total_amount_90d")
if not re.fullmatch(r"[a-z_][a-z0-9_]*", _AUM_COLUMN):
    raise ValueError(f"INTEL_AUM_COLUMN must be a plain identifier, got {_AUM_COLUMN!r}")


class IntelligenceRepository:
    """Read-only aggregations for the /api/v1/intelligence/* endpoints."""

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
    # Snapshot dates
    # ------------------------------------------------------------------

    def latest_feature_date(self) -> date | None:
        def _q():
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute("SELECT MAX(as_of_date) FROM customer_features")
                return cur.fetchone()[0]
            finally:
                conn.close()
        return self._retry(_q, "latest_feature_date")

    # ------------------------------------------------------------------
    # AUM proxy + segment + branch (customer_features)
    # ------------------------------------------------------------------

    def customer_value_profiles(self, as_of_date: date) -> list[dict]:
        """Per-customer AUM, segment, branch for the snapshot date.

        AUM comes from the INTEL_AUM_COLUMN (pilot proxy: total_amount_90d);
        rows with NULL get 0.
        """
        def _q():
            conn = self._connect()
            try:
                cur = conn.cursor(cursor_factory=extras.RealDictCursor)
                cur.execute(
                    f"""
                    SELECT customer_id,
                           COALESCE({_AUM_COLUMN}, 0) AS current_aum,
                           customer_segment,
                           prof_primary_branch AS branch_id
                    FROM customer_features
                    WHERE as_of_date = %(d)s
                    """,
                    {"d": as_of_date},
                )
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()
        return self._retry(_q, f"customer_value_profiles({as_of_date})")

    # ------------------------------------------------------------------
    # Lifecycle states
    # ------------------------------------------------------------------

    def state_counts(self, as_of_date: date) -> dict[str, int]:
        def _q():
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT state, COUNT(*)
                    FROM customer_states
                    WHERE as_of_date = %(d)s
                    GROUP BY state
                    """,
                    {"d": as_of_date},
                )
                return {s: int(n) for s, n in cur.fetchall()}
            finally:
                conn.close()
        return self._retry(_q, f"state_counts({as_of_date})")

    def transition_matrix(self, anchor: date, window_days: int = 30) -> dict:
        """Raw from→to counts over the trailing window + per-customer state age.

        Window is anchored to the snapshot as_of_date, not CURRENT_DATE —
        the pilot dataset's "now" is its latest feature date.
        Returns {"states": [...], "matrix": [[int]], "labels" set separately}.
        """
        def _q():
            conn = self._connect()
            try:
                cur = conn.cursor(cursor_factory=extras.RealDictCursor)
                cur.execute(
                    """
                    SELECT from_state, to_state, COUNT(*) AS n
                    FROM state_transitions
                    WHERE transition_date >= %(anchor)s - %(w)s::int
                      AND transition_date <= %(anchor)s
                    GROUP BY from_state, to_state
                    """,
                    {"anchor": anchor, "w": window_days},
                )
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()
        rows = self._retry(_q, "transition_matrix")
        states = ["NEW", "ACTIVE", "GROWING", "AT_RISK", "DORMANT", "CHURNED"]
        idx = {s: i for i, s in enumerate(states)}
        matrix = [[0] * len(states) for _ in states]
        for r in rows:
            i, j = idx.get(r["from_state"]), idx.get(r["to_state"])
            if i is not None and j is not None:
                matrix[i][j] = int(r["n"])
        return {"states": states, "matrix": matrix}

    def churned_customers(self, as_of_date: date, limit: int = 200) -> list[dict]:
        """CHURNED customers newest-first, with churn recency + 180d value signal.

        total_amount_180d is the win-back value proxy: churned customers have
        no recent activity, so their live CLV percentile is ~0 by construction —
        historical transaction value ranks who is worth winning back.
        """
        def _q():
            conn = self._connect()
            try:
                cur = conn.cursor(cursor_factory=extras.RealDictCursor)
                cur.execute(
                    """
                    SELECT cs.customer_id,
                           cs.as_of_date,
                           st.to_state,
                           st.transition_date AS churned_on,
                           COALESCE(
                             (cs.as_of_date - st.transition_date), 0
                           ) AS days_since_churn,
                           COALESCE(f.total_amount_180d, 0) AS value_180d
                    FROM customer_states cs
                    LEFT JOIN LATERAL (
                        SELECT transition_date, to_state
                        FROM state_transitions t
                        WHERE t.customer_id = cs.customer_id
                          AND t.to_state = 'CHURNED'
                        ORDER BY transition_date DESC
                        LIMIT 1
                    ) st ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT total_amount_180d
                        FROM customer_features f
                        WHERE f.customer_id = cs.customer_id
                          AND f.as_of_date = cs.as_of_date
                        LIMIT 1
                    ) f ON TRUE
                    WHERE cs.state = 'CHURNED'
                      AND cs.as_of_date = %(d)s
                    ORDER BY st.transition_date DESC NULLS LAST
                    LIMIT %(lim)s
                    """,
                    {"d": as_of_date, "lim": limit},
                )
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()
        return self._retry(_q, f"churned_customers({as_of_date})")

    # ------------------------------------------------------------------
    # decision_outcomes (ROI)
    # ------------------------------------------------------------------

    def revenue_protected_mtd(self) -> float:
        def _q():
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT COALESCE(SUM(revenue_protected_amount), 0)
                    FROM decision_outcomes
                    WHERE accepted_flag
                      AND date_trunc('month', created_at) = date_trunc('month', CURRENT_DATE)
                    """
                )
                return float(cur.fetchone()[0])
            finally:
                conn.close()
        return self._retry(_q, "revenue_protected_mtd")

    def roi_by_branch(self) -> list[dict]:
        """Per-branch intervention ROI: pilot/control split comes from the flag."""
        def _q():
            conn = self._connect()
            try:
                cur = conn.cursor(cursor_factory=extras.RealDictCursor)
                cur.execute(
                    """
                    SELECT branch_id,
                           is_pilot_branch,
                           COUNT(*) AS interventions,
                           COUNT(*) FILTER (WHERE accepted_flag) AS accepted,
                           -- Retention is measured on the accepted cohort only;
                           -- declined customers may retain organically.
                           COUNT(*) FILTER (WHERE accepted_flag AND retained_90d) AS retained,
                           COUNT(*) FILTER (WHERE accepted_flag AND retained_90d IS NOT NULL)
                               AS measured_accepted,
                           COALESCE(SUM(cost_amount), 0) AS total_cost,
                           COALESCE(SUM(revenue_protected_amount), 0) AS total_revenue
                    FROM decision_outcomes
                    WHERE branch_id IS NOT NULL
                    GROUP BY branch_id, is_pilot_branch
                    ORDER BY total_revenue DESC
                    """
                )
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()
        return self._retry(_q, "roi_by_branch")

    def revenue_trend(self, months: int = 5) -> list[dict]:
        """Monthly accepted revenue_protected totals for the trend chart."""
        def _q():
            conn = self._connect()
            try:
                cur = conn.cursor(cursor_factory=extras.RealDictCursor)
                cur.execute(
                    """
                    SELECT to_char(date_trunc('month', created_at), 'Mon') AS month,
                           COALESCE(SUM(revenue_protected_amount), 0) AS revenue
                    FROM decision_outcomes
                    WHERE created_at >= date_trunc('month', CURRENT_DATE) - (%(m)s::int - 1) * interval '1 month'
                    GROUP BY 1, date_trunc('month', created_at)
                    ORDER BY date_trunc('month', created_at)
                    """,
                    {"m": months},
                )
                return [{"month": r["month"], "revenue": float(r["revenue"])} for r in cur.fetchall()]
            finally:
                conn.close()
        return self._retry(_q, "revenue_trend")

    def roi_totals(self) -> dict:
        """revenue_protected = initial CLV of retained customers; cost = spend + flat RM cost."""
        def _q():
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT
                      COALESCE(SUM(clv_score) FILTER (WHERE retained_90d), 0) AS revenue_protected,
                      COALESCE(SUM(cost_amount), 0) +
                        COUNT(*) FILTER (WHERE channel IN ('RM_CALL','RM_DIRECT')) * 25.0
                        AS intervention_cost
                    FROM decision_outcomes
                    """
                )
                rev, cost = cur.fetchone()
                return {"revenue_protected": float(rev), "intervention_cost": float(cost)}
            finally:
                conn.close()
        return self._retry(_q, "roi_totals")
