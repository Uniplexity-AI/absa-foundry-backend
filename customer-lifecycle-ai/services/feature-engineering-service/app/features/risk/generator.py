"""Risk Generator — Domain 6 of the Customer Feature Store.

Computes observable risk indicators from transaction data.
Descriptive, NOT predictive — all features are verifiable facts.

Stage 1: FROM-subquery for ratios + volatility + dormancy (5 features).
Stage 2: FROM-subquery for unusual-channel detection (1 feature).
"""

from __future__ import annotations

from datetime import date

import psycopg2


class RiskGenerator:
    """Generates risk indicator features from transaction data."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def generate(self, as_of_date: date) -> dict:
        """Run all risk features in two optimized UPDATE statements.

        Stage 1: High-value ratio, volatility, reversal ratio,
                 cash-heavy ratio, dormant indicator (single scan).
        Stage 2: Unusual channel flag (channel-level comparison
                 across two time windows).
        """
        results = {}

        with self._conn.cursor() as cur:
            # Stage 1: Aggregation-based risk features + dormancy
            cur.execute(
                """
                UPDATE customer_features cf
                SET
                    risk_high_value_txn_ratio_90d = ROUND(COALESCE(
                        agg.high_value_cnt::float / NULLIF(agg.total_cnt, 0), 0
                    )::numeric, 2),
                    risk_txn_volatility_90d = CASE
                        WHEN agg.total_cnt > 0 AND agg.amount_avg > 0
                        THEN ROUND((COALESCE(agg.amount_stddev, 0)
                              / NULLIF(agg.amount_avg, 0))::numeric, 2)
                        ELSE NULL
                    END,
                    risk_reversal_ratio_90d = ROUND(COALESCE(
                        agg.reversal_cnt::float / NULLIF(agg.total_cnt, 0), 0
                    )::numeric, 2),
                    risk_cash_heavy_ratio_90d = ROUND(COALESCE(
                        agg.cash_cnt::float / NULLIF(agg.total_cnt, 0), 0
                    )::numeric, 2),
                    risk_dormant_indicator = (
                        COALESCE(cf.days_since_last_txn, 999) > 90
                    )
                FROM (
                    SELECT
                        t.customer_id,
                        COUNT(*) AS total_cnt,
                        COUNT(*) FILTER (WHERE t.amount > 10000) AS high_value_cnt,
                        COUNT(*) FILTER (WHERE t.transaction_type = 'REVERSAL') AS reversal_cnt,
                        COUNT(*) FILTER (WHERE t.channel IN ('ATM', 'BRANCH')) AS cash_cnt,
                        STDDEV(t.amount) AS amount_stddev,
                        AVG(t.amount) AS amount_avg
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
            results["risk_ratios_dormant"] = cur.rowcount

            # Stage 2: Unusual channel flag
            # A channel used in last 30 days that was NOT used in prior 150 days.
            cur.execute(
                """
                UPDATE customer_features cf
                SET risk_unusual_channel_flag = agg.has_unusual
                FROM (
                    SELECT
                        c30.customer_id,
                        BOOL_OR(c180.channel IS NULL) AS has_unusual
                    FROM (
                        SELECT DISTINCT customer_id, channel
                        FROM customer_transactions_clean
                        WHERE transaction_date::date > (%(d)s::date - INTERVAL '30 days')
                          AND transaction_date::date <= %(d)s::date
                    ) c30
                    LEFT JOIN (
                        SELECT DISTINCT customer_id, channel
                        FROM customer_transactions_clean
                        WHERE transaction_date::date > (%(d)s::date - INTERVAL '180 days')
                          AND transaction_date::date <= (%(d)s::date - INTERVAL '30 days')
                    ) c180
                        ON c30.customer_id = c180.customer_id
                       AND c30.channel = c180.channel
                    GROUP BY c30.customer_id
                ) agg
                WHERE cf.customer_id = agg.customer_id
                  AND cf.as_of_date = %(d)s::date
                """,
                {"d": as_of_date},
            )
            results["risk_unusual_channel"] = cur.rowcount

            self._conn.commit()

        return results
