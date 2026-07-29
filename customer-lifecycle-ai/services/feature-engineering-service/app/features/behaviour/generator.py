"""
Behaviour Generator — Domain 2 of the Customer Feature Store.

Computes transaction patterns, engagement metrics, and activity levels.
Uses a single FROM-subquery approach: one scan of customer_transactions_clean
computes all aggregations, then a single UPDATE writes all features.

Scoring weights and thresholds are configurable via FeatureConfig
(env: FE_ENGAGEMENT_RECENCY_WEIGHT, etc.).  Defaults match the architecture doc.

All features are point-in-time correct.
"""

from __future__ import annotations

from datetime import date

import psycopg2

from app.config.settings import Settings


class BehaviourGenerator:
    """Generates behaviour, engagement, and activity features.

    Scoring weights and windows are configurable via class-level defaults
    or per-instance override.  The pipeline passes only a connection;
    the generator loads its own config.
    """

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn
        self._cfg = Settings().features

    def generate(self, as_of_date: date) -> dict:
        """Run all behaviour features in a single optimized UPDATE.

        Uses a FROM-subquery that aggregates all transaction windows
        in one pass, then writes 10 feature columns at once.
        """
        with self._conn.cursor() as cur:
            cfg = self._cfg
            cur.execute(
                """
                UPDATE customer_features cf
                SET
                    behav_txn_count_7d       = agg.txn_count_7d,
                    behav_active_days_90d    = agg.active_days_90d,
                    behav_inactive_days_90d  = %(inactive_window)s - COALESCE(agg.active_days_90d, 0),
                    behav_activity_consistency = ROUND((COALESCE(agg.active_days_90d, 0)::float / %(consistency_window)s::float)::numeric, 2),
                    behav_recency_score = LEAST(%(recency_weight)s, GREATEST(0,
                        %(recency_weight)s - LEAST(%(recency_weight)s,
                            (COALESCE(agg.days_since_last, %(max_recency)s)::float / %(max_recency)s::float) * %(recency_weight)s
                        )
                    )),
                    behav_frequency_score = LEAST(%(frequency_weight)s, GREATEST(0,
                        (COALESCE(agg.txn_count_30d, 0)::float / %(max_freq_txn)s::float) * %(frequency_weight)s
                    )),
                    behav_diversity_score = LEAST(%(diversity_weight)s, GREATEST(0,
                        (COALESCE(agg.channels, 0)::float / %(max_channels)s::float) * (%(diversity_weight)s::float / 2.0)
                        + (COALESCE(agg.txn_types, 0)::float / %(max_types)s::float) * (%(diversity_weight)s::float / 2.0)
                    )),
                    engagement_score = ROUND((
                        LEAST(%(recency_weight)s, GREATEST(0,
                            %(recency_weight)s - LEAST(%(recency_weight)s,
                                (COALESCE(agg.days_since_last, %(max_recency)s)::float / %(max_recency)s::float) * %(recency_weight)s
                            )
                        ))
                        + LEAST(%(frequency_weight)s, GREATEST(0,
                            (COALESCE(agg.txn_count_30d, 0)::float / %(max_freq_txn)s::float) * %(frequency_weight)s
                        ))
                        + LEAST(%(diversity_weight)s, GREATEST(0,
                            (COALESCE(agg.channels, 0)::float / %(max_channels)s::float) * (%(diversity_weight)s::float / 2.0)
                            + (COALESCE(agg.txn_types, 0)::float / %(max_types)s::float) * (%(diversity_weight)s::float / 2.0)
                        ))
                    )::numeric, 0),
                    -- Legacy backward-compat columns
                    txn_frequency_trend = ROUND((COALESCE(agg.active_days_90d, 0)::float / %(consistency_window)s::float)::numeric, 2),
                    inactivity_streak_days = %(inactive_window)s - COALESCE(agg.active_days_90d, 0)
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
                {
                    "d": as_of_date,
                    "recency_weight": cfg.engagement_recency_weight,
                    "frequency_weight": cfg.engagement_frequency_weight,
                    "diversity_weight": cfg.engagement_diversity_weight,
                    "max_recency": cfg.engagement_max_recency_days,
                    "max_freq_txn": cfg.engagement_max_frequency_txn,
                    "max_channels": cfg.engagement_max_diversity_channels,
                    "max_types": cfg.engagement_max_diversity_types,
                    "consistency_window": cfg.activity_consistency_window_days,
                    "inactive_window": cfg.inactive_days_window,
                },
            )
            count = cur.rowcount
            self._conn.commit()

        return {"behaviour_all": count}

