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
    (
        SELECT channel FROM (
            SELECT channel, COUNT(*) as cnt, MAX(transaction_date) as last_used
            FROM customer_transactions_clean c2
            WHERE c2.customer_id = t.customer_id
              AND c2.transaction_date::date <= %(as_of_date)s::date
              AND c2.transaction_date::date > (%(as_of_date)s::date - INTERVAL '90 days')
            GROUP BY channel
            ORDER BY cnt DESC, last_used DESC
            LIMIT 1
        ) s
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

FETCH_SQL = """
SELECT customer_id, as_of_date,
       days_since_last_txn, days_since_first_txn,
       txn_count_30d, txn_count_90d, txn_count_180d,
       avg_days_between_txn,
       total_amount_90d, avg_amount_90d, total_amount_180d,
       amount_growth_ratio,
       distinct_channels_90d, distinct_txn_types_90d,
       dominant_channel, amount_stddev_90d,
       computed_at
FROM customer_features
WHERE customer_id = %s AND as_of_date = %s
"""

LATEST_SQL = """
SELECT customer_id, as_of_date,
       days_since_last_txn, days_since_first_txn,
       txn_count_30d, txn_count_90d, txn_count_180d,
       avg_days_between_txn,
       total_amount_90d, avg_amount_90d, total_amount_180d,
       amount_growth_ratio,
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
        """Compute features for all customers as of a given date.

        Uses INSERT ... ON CONFLICT DO UPDATE (upsert) for idempotency.
        Customers with zero transactions before as_of_date are excluded
        by the GROUP BY (they produce no rows).

        Returns:
            Dict with customers_processed, rows_upserted, duration_seconds.
        """
        t0 = time.monotonic()
        conn = psycopg2.connect(self._conn_str)
        try:
            cur = conn.cursor()
            cur.execute(FEATURE_SQL, {"as_of_date": as_of_date.isoformat()})
            conn.commit()
            rows = cur.rowcount
        finally:
            conn.close()
        elapsed = time.monotonic() - t0
        # Count distinct customers for this as_of_date
        customers = self._count_customers(as_of_date)
        return {
            "as_of_date": as_of_date,
            "customers_processed": customers,
            "rows_upserted": rows,
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
