"""
Behaviour Generator — Domain 2 of the Customer Feature Store.

Computes transaction patterns, engagement metrics, and activity levels.
Uses a single FROM-subquery approach: one scan of customer_transactions_clean
computes all aggregations, then a single UPDATE writes all features.

All features are point-in-time correct.
"""

from __future__ import annotations

from datetime import date

import psycopg2


class BehaviourGenerator:
    """Generates behaviour, engagement, and activity features."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def generate(self, as_of_date: date) -> dict:
        """Run all behaviour features in a single optimized UPDATE.

        Uses a FROM-subquery that aggregates all transaction windows
        in one pass, then writes 10 feature columns at once.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE customer_features cf
                SET
                    behav_txn_count_7d       = agg.txn_count_7d,
                    behav_active_days_90d    = agg.active_days_90d,
                    behav_inactive_days_90d  = 90 - COALESCE(agg.active_days_90d, 0),
                    behav_activity_consistency = ROUND((COALESCE(agg.active_days_90d, 0)::float / 90.0)::numeric, 2),
                    behav_recency_score = LEAST(40, GREATEST(0,
                        40.0 - LEAST(40.0,
                            (COALESCE(agg.days_since_last, 90)::float / 90.0) * 40.0
                        )
                    )),
                    behav_frequency_score = LEAST(35, GREATEST(0,
                        (COALESCE(agg.txn_count_30d, 0)::float / 30.0) * 35.0
                    )),
                    behav_diversity_score = LEAST(25, GREATEST(0,
                        (COALESCE(agg.channels, 0)::float / 5.0) * 12.5
                        + (COALESCE(agg.txn_types, 0)::float / 5.0) * 12.5
                    )),
                    engagement_score = ROUND((
                        LEAST(40, GREATEST(0,
                            40.0 - LEAST(40.0,
                                (COALESCE(agg.days_since_last, 90)::float / 90.0) * 40.0
                            )
                        ))
                        + LEAST(35, GREATEST(0,
                            (COALESCE(agg.txn_count_30d, 0)::float / 30.0) * 35.0
                        ))
                        + LEAST(25, GREATEST(0,
                            (COALESCE(agg.channels, 0)::float / 5.0) * 12.5
                            + (COALESCE(agg.txn_types, 0)::float / 5.0) * 12.5
                        ))
                    )::numeric, 0),
                    -- Legacy backward-compat columns
                    txn_frequency_trend = ROUND((COALESCE(agg.active_days_90d, 0)::float / 90.0)::numeric, 2),
                    inactivity_streak_days = 90 - COALESCE(agg.active_days_90d, 0)
                FROM (
                    SELECT
                        t.customer_id,
                        (%(d)s::date - MAX(t.transaction_date)::date)::int AS days_since_last,
                        COUNT(*) FILTER (
                            WHERE t.transaction_date::date > (%(d)s::date - INTERVAL '7 days')
                        ) AS txn_count_7d,
                        COUNT(*) FILTER (
                            WHERE t.transaction_date::date > (%(d)s::date - INTERVAL '30 days')
                        ) AS txn_count_30d,
                        COUNT(DISTINCT t.transaction_date::date) FILTER (
                            WHERE t.transaction_date::date > (%(d)s::date - INTERVAL '90 days')
                        ) AS active_days_90d,
                        COUNT(DISTINCT t.channel) FILTER (
                            WHERE t.transaction_date::date > (%(d)s::date - INTERVAL '90 days')
                        ) AS channels,
                        COUNT(DISTINCT t.transaction_type) FILTER (
                            WHERE t.transaction_date::date > (%(d)s::date - INTERVAL '90 days')
                        ) AS txn_types
                    FROM customer_transactions_clean t
                    WHERE t.transaction_date::date <= %(d)s::date
                    GROUP BY t.customer_id
                ) agg
                WHERE cf.customer_id = agg.customer_id
                  AND cf.as_of_date = %(d)s::date
                """,
                {"d": as_of_date},
            )
            count = cur.rowcount
            self._conn.commit()

        return {"behaviour_all": count}

