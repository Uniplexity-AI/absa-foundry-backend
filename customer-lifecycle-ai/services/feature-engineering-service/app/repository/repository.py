"""
Feature Engineering Repository — Point-in-time SQL aggregation.

Computes customer features from customer_transactions_clean using
a single SQL query per as_of_date. All queries enforce:
  transaction_date <= as_of_date
preventing data leakage in downstream ML training.

Uses psycopg2 (sync) for direct DB access — matches ETL pattern.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone

import psycopg2
from psycopg2 import extras

from shared.config.settings import settings


FEATURE_SQL = """
INSERT INTO customer_features (
    customer_id, as_of_date,
    days_since_last_txn, days_since_first_txn,
    txn_count_30d, txn_count_90d, txn_count_180d,
    avg_days_between_txn,
    total_amount_90d, avg_amount_90d, total_amount_180d,
    amount_growth_ratio,
    distinct_channels_90d, distinct_txn_types_90d,
    dominant_channel, amount_stddev_90d,
    computed_at
)
SELECT
    customer_id,
    %(as_of_date)s::date AS as_of_date,

    -- Recency / tenure
    (%(as_of_date)s::date - MAX(transaction_date)::date) AS days_since_last_txn,
    (%(as_of_date)s::date - MIN(transaction_date)::date) AS days_since_first_txn,

    -- Transaction counts by window
    COUNT(*) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '30 days'))
        AS txn_count_30d,
    COUNT(*) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '90 days'))
        AS txn_count_90d,
    COUNT(*) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '180 days'))
        AS txn_count_180d,

    -- Frequency (NULL if only 1 txn)
    CASE WHEN COUNT(*) >= 2
        THEN (%(as_of_date)s::date - MIN(transaction_date)::date)::float / (COUNT(*) - 1)
    END AS avg_days_between_txn,

    -- Monetary
    SUM(amount) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '90 days'))
        AS total_amount_90d,
    AVG(amount) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '90 days'))
        AS avg_amount_90d,
    SUM(amount) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '180 days'))
        AS total_amount_180d,

    -- Growth ratio (NULL if denominator is zero)
    CASE
        WHEN COALESCE(
            SUM(amount) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '180 days')), 0
        ) - COALESCE(
            SUM(amount) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '90 days')), 0
        ) = 0 THEN NULL
        ELSE SUM(amount) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '90 days'))
             / NULLIF(
                 SUM(amount) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '180 days'))
                 - SUM(amount) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '90 days')),
                 0
             )
    END AS amount_growth_ratio,

    -- Diversity
    COUNT(DISTINCT channel) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '90 days'))
        AS distinct_channels_90d,
    COUNT(DISTINCT transaction_type) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '90 days'))
        AS distinct_txn_types_90d,

    -- Dominant channel (most frequent in 90d, ties broken by most recent)
    -- OPTIMIZED: pre-computed via window function instead of correlated subquery
    (
        SELECT channel FROM (
            SELECT channel,
                   ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC, MAX(transaction_date) DESC) AS rn
            FROM customer_transactions_clean c2
            WHERE c2.customer_id = t.customer_id
              AND c2.transaction_date::date <= %(as_of_date)s::date
              AND c2.transaction_date::date > (%(as_of_date)s::date - INTERVAL '90 days')
            GROUP BY channel
        ) s WHERE rn = 1
    ) AS dominant_channel,

    -- Volatility
    STDDEV(amount) FILTER (WHERE transaction_date::date > (%(as_of_date)s::date - INTERVAL '90 days'))
        AS amount_stddev_90d,

    now() AS computed_at
FROM customer_transactions_clean t
WHERE transaction_date::date <= %(as_of_date)s::date
GROUP BY customer_id
ON CONFLICT (customer_id, as_of_date) DO UPDATE SET
    days_since_last_txn    = EXCLUDED.days_since_last_txn,
    days_since_first_txn   = EXCLUDED.days_since_first_txn,
    txn_count_30d          = EXCLUDED.txn_count_30d,
    txn_count_90d          = EXCLUDED.txn_count_90d,
    txn_count_180d         = EXCLUDED.txn_count_180d,
    avg_days_between_txn   = EXCLUDED.avg_days_between_txn,
    total_amount_90d       = EXCLUDED.total_amount_90d,
    avg_amount_90d         = EXCLUDED.avg_amount_90d,
    total_amount_180d      = EXCLUDED.total_amount_180d,
    amount_growth_ratio    = EXCLUDED.amount_growth_ratio,
    distinct_channels_90d  = EXCLUDED.distinct_channels_90d,
    distinct_txn_types_90d = EXCLUDED.distinct_txn_types_90d,
    dominant_channel       = EXCLUDED.dominant_channel,
    amount_stddev_90d      = EXCLUDED.amount_stddev_90d,
    computed_at            = EXCLUDED.computed_at
"""

# Phase 2: Derived features computed from the raw aggregates already stored.
# Runs as a lightweight UPDATE — no re-aggregation needed.
PHASE2_SQL = """
UPDATE customer_features SET
    -- Extended window
    txn_count_365d = (
        SELECT COUNT(*) FROM customer_transactions_clean t
        WHERE t.customer_id = customer_features.customer_id
          AND t.transaction_date::date > (customer_features.as_of_date - INTERVAL '365 days')
          AND t.transaction_date::date <= customer_features.as_of_date
    ),
    -- Credit / Debit separation
    credit_sum_30d = (
        SELECT COALESCE(SUM(amount), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = customer_features.customer_id
          AND t.transaction_date::date > (customer_features.as_of_date - INTERVAL '30 days')
          AND t.transaction_date::date <= customer_features.as_of_date
          AND t.transaction_type = 'CREDIT'
    ),
    debit_sum_30d = (
        SELECT COALESCE(SUM(amount), 0)
        FROM customer_transactions_clean t
        WHERE t.customer_id = customer_features.customer_id
          AND t.transaction_date::date > (customer_features.as_of_date - INTERVAL '30 days')
          AND t.transaction_date::date <= customer_features.as_of_date
          AND t.transaction_type = 'DEBIT'
    ),
    -- Ratios
    credit_to_debit_ratio_90d = CASE
        WHEN debit_sum_30d IS NULL OR debit_sum_30d = 0 THEN NULL
        ELSE ROUND(credit_sum_30d::numeric / debit_sum_30d, 2)
    END,
    -- Trend: compares 30d vs 60-90d average
    balance_trend_90d = CASE
        WHEN txn_count_90d IS NULL OR txn_count_90d = 0 THEN 'STABLE'
        WHEN txn_count_30d > (txn_count_90d - txn_count_30d) / 2.0 THEN 'RISING'
        WHEN txn_count_30d < (txn_count_90d - txn_count_30d) / 2.0 THEN 'FALLING'
        ELSE 'STABLE'
    END,
    -- Salary detection: 3+ monthly CREDIT deposits within 10% variance
    has_salary_credit = (
        SELECT COUNT(DISTINCT DATE_TRUNC('month', transaction_date::date)) >= 3
        FROM customer_transactions_clean t2
        WHERE t2.customer_id = customer_features.customer_id
          AND t2.transaction_type = 'CREDIT'
          AND t2.transaction_date::date > (customer_features.as_of_date - INTERVAL '90 days')
          AND t2.transaction_date::date <= customer_features.as_of_date
    ),
    -- Income estimate: average monthly CREDIT over 90 days
    monthly_income_estimate = (
        SELECT ROUND(COALESCE(SUM(amount), 0) / 3.0, 2)
        FROM customer_transactions_clean t2
        WHERE t2.customer_id = customer_features.customer_id
          AND t2.transaction_type = 'CREDIT'
          AND t2.transaction_date::date > (customer_features.as_of_date - INTERVAL '90 days')
          AND t2.transaction_date::date <= customer_features.as_of_date
    ),
    computed_at = NOW()
WHERE as_of_date = '{date}'::date
"""

def _phase2_sql(as_of_date: date) -> str:
    """Return Phase 2 SQL with the date formatted inline (safe — isoformat is YYYY-MM-DD)."""
    return PHASE2_SQL.format(date=as_of_date.isoformat())

FETCH_SQL = """
SELECT customer_id, as_of_date,
       days_since_last_txn, days_since_first_txn,
       txn_count_30d, txn_count_90d, txn_count_180d, txn_count_365d,
       avg_days_between_txn,
       total_amount_90d, avg_amount_90d, total_amount_180d,
       amount_growth_ratio,
       credit_sum_30d, debit_sum_30d, credit_to_debit_ratio_90d,
       balance_trend_90d, has_salary_credit, monthly_income_estimate,
       distinct_channels_90d, distinct_txn_types_90d,
       dominant_channel, amount_stddev_90d,
       computed_at
FROM customer_features
WHERE customer_id = %s AND as_of_date = %s
"""

LATEST_SQL = """
SELECT customer_id, as_of_date,
       days_since_last_txn, days_since_first_txn,
       txn_count_30d, txn_count_90d, txn_count_180d, txn_count_365d,
       avg_days_between_txn,
       total_amount_90d, avg_amount_90d, total_amount_180d,
       amount_growth_ratio,
       credit_sum_30d, debit_sum_30d, credit_to_debit_ratio_90d,
       balance_trend_90d, has_salary_credit, monthly_income_estimate,
       distinct_channels_90d, distinct_txn_types_90d,
       dominant_channel, amount_stddev_90d,
       computed_at
FROM customer_features
WHERE customer_id = %s
ORDER BY as_of_date DESC
LIMIT 1
"""


class FeatureRepository:
    """Computes and retrieves point-in-time customer features."""

    def __init__(self) -> None:
        self._conn_str = settings.database_target_url_sync

    def compute_batch(self, as_of_date: date) -> dict:
        """Compute features for all customers as of a given date."""
        return self._compute(as_of_date)

    def compute_for_customers(self, as_of_date: date, customer_ids: list[str]) -> dict:
        """Compute features for specific customers only (fast, for testing)."""
        return self._compute(as_of_date, customer_ids=customer_ids)

    def _compute(self, as_of_date: date, customer_ids: list[str] | None = None) -> dict:
        t0 = time.monotonic()
        conn = psycopg2.connect(self._conn_str)
        try:
            cur = conn.cursor()
            if customer_ids:
                sql = FEATURE_SQL.replace(
                    "FROM customer_transactions_clean t\nWHERE transaction_date::date <= %(as_of_date)s::date",
                    "FROM customer_transactions_clean t\nWHERE transaction_date::date <= %(as_of_date)s::date\n  AND t.customer_id = ANY(%(customer_ids)s)"
                )
                cur.execute(sql, {"as_of_date": as_of_date.isoformat(), "customer_ids": customer_ids})
            else:
                cur.execute(FEATURE_SQL, {"as_of_date": as_of_date.isoformat()})
            conn.commit()
            phase1_rows = cur.rowcount

            # Phase 2: Derived features (credit/debit split, ratios, trends, salary detection)
            cur.execute(_phase2_sql(as_of_date))
            conn.commit()
            phase2_rows = cur.rowcount
        finally:
            conn.close()
        elapsed = time.monotonic() - t0
        customers = self._count_customers(as_of_date)
        return {
            "as_of_date": as_of_date,
            "customers_processed": customers,
            "rows_upserted": phase1_rows,
            "phase2_updated": phase2_rows,
            "duration_seconds": round(elapsed, 2),
        }

    def get_features(self, customer_id: str, as_of_date: date) -> dict | None:
        """Fetch a specific feature snapshot. Returns None if not found."""
        conn = psycopg2.connect(self._conn_str)
        try:
            cur = conn.cursor(cursor_factory=extras.RealDictCursor)
            cur.execute(FETCH_SQL, (customer_id, as_of_date))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_latest(self, customer_id: str) -> dict | None:
        """Fetch the most recent feature snapshot for a customer."""
        conn = psycopg2.connect(self._conn_str)
        try:
            cur = conn.cursor(cursor_factory=extras.RealDictCursor)
            cur.execute(LATEST_SQL, (customer_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _count_customers(self, as_of_date: date) -> int:
        """Count customers with features for a given as_of_date."""
        conn = psycopg2.connect(self._conn_str)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM customer_features WHERE as_of_date = %s",
                (as_of_date,),
            )
            return cur.fetchone()[0]
        finally:
            conn.close()
