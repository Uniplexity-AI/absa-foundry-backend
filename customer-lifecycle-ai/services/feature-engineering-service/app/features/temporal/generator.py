"""Temporal Generator — Domain 7 of the Customer Feature Store.

Computes time-based behavioural patterns: day-of-week and payday cycles.
Time-of-day features (morning/afternoon/evening) are deferred — they
require TIMESTAMP-precision transaction_date, currently DATE-only.
"""

from __future__ import annotations

from datetime import date

import psycopg2


class TemporalGenerator:
    """Generates temporal pattern features from transaction data."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def generate(self, as_of_date: date) -> dict:
        """Run temporal features in a single optimized UPDATE.

        Computes 3 of 6 features in one FROM-subquery scan:
        - weekend / weekday ratios (EXTRACT DOW works with DATE)
        - payday ratio (EXTRACT DAY works with DATE)

        Time-of-day features (morning/afternoon/evening) remain NULL
        until TIMESTAMP transaction data is available.
        """
        results = {}

        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE customer_features cf
                SET
                    temp_weekend_txn_ratio_90d = ROUND(COALESCE(
                        agg.weekend_cnt::float / NULLIF(agg.total_cnt, 0), 0
                    )::numeric, 2),
                    temp_weekday_txn_ratio_90d = ROUND(COALESCE(
                        agg.weekday_cnt::float / NULLIF(agg.total_cnt, 0), 0
                    )::numeric, 2),
                    temp_payday_activity_ratio_90d = ROUND(COALESCE(
                        agg.payday_cnt::float / NULLIF(agg.total_cnt, 0), 0
                    )::numeric, 2)
                FROM (
                    SELECT
                        t.customer_id,
                        COUNT(*) AS total_cnt,
                        COUNT(*) FILTER (
                            WHERE EXTRACT(DOW FROM t.transaction_date) IN (0, 6)
                        ) AS weekend_cnt,
                        COUNT(*) FILTER (
                            WHERE EXTRACT(DOW FROM t.transaction_date) BETWEEN 1 AND 5
                        ) AS weekday_cnt,
                        COUNT(*) FILTER (
                            WHERE EXTRACT(DAY FROM t.transaction_date) BETWEEN 25 AND 31
                               OR EXTRACT(DAY FROM t.transaction_date) BETWEEN 1 AND 5
                        ) AS payday_cnt
                    FROM customer_transactions_clean t
                    WHERE t.transaction_date::date > (%(d)s::date - INTERVAL '90 days')
                      AND t.transaction_date::date <= %(d)s::date
                    GROUP BY t.customer_id
                ) agg
                WHERE cf.customer_id = agg.customer_id
                  AND cf.as_of_date = %(d)s::date
                """,
                {"d": as_of_date},
            )
            results["temporal_all"] = cur.rowcount
            self._conn.commit()

        return results
