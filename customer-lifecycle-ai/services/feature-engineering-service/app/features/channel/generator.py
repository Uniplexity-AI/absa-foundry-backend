"""
Channel Generator — Domain 4 of the Customer Feature Store.

Computes channel preference, digital adoption, and channel entropy features.
All stages use optimized FROM-subquery approach (single scan per stage,
no correlated subqueries).
"""

from __future__ import annotations

from datetime import date

import psycopg2


class ChannelGenerator:
    """Generates channel usage and digital adoption features."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def generate(self, as_of_date: date) -> dict:
        """Run all channel feature SQL statements.

        Stage 1: Channel ratios + digital adoption (single FROM-subquery).
        Stage 2: Channel entropy (single FROM-subquery with per-channel grouping).

        Returns:
            Dict with row counts per feature.
        """
        results = {}

        with self._conn.cursor() as cur:
            # Stage 1: Channel ratios + digital adoption (single scan)
            cur.execute(
                """
                UPDATE customer_features cf
                SET
                    chan_mobile_ratio_90d = ROUND(COALESCE(
                        agg.mobile_cnt::float / NULLIF(agg.total_cnt, 0), 0
                    )::numeric, 2),
                    chan_atm_ratio_90d = ROUND(COALESCE(
                        agg.atm_cnt::float / NULLIF(agg.total_cnt, 0), 0
                    )::numeric, 2),
                    chan_branch_ratio_90d = ROUND(COALESCE(
                        agg.branch_cnt::float / NULLIF(agg.total_cnt, 0), 0
                    )::numeric, 2),
                    chan_digital_adoption_score = ROUND(
                        COALESCE(
                            (agg.mobile_cnt + agg.online_cnt)::float
                            / NULLIF(agg.total_cnt, 0) * 100.0, 0
                        )::numeric, 0
                    )
                FROM (
                    SELECT
                        t.customer_id,
                        COUNT(*) FILTER (WHERE t.channel = 'MOBILE') AS mobile_cnt,
                        COUNT(*) FILTER (WHERE t.channel = 'ATM') AS atm_cnt,
                        COUNT(*) FILTER (WHERE t.channel = 'BRANCH') AS branch_cnt,
                        COUNT(*) FILTER (WHERE t.channel IN ('ONLINE', 'INTERNET')) AS online_cnt,
                        COUNT(*) AS total_cnt
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
            results["channel_ratios_digital"] = cur.rowcount

            # Stage 2: Channel entropy (normalized Shannon entropy via FROM-subquery)
            cur.execute(
                """
                UPDATE customer_features cf
                SET chan_channel_entropy = agg.entropy
                FROM (
                    SELECT
                        cc.customer_id,
                        ROUND(
                            (-1.0 * SUM(
                                (cc.cnt::float / NULLIF(cs.total, 0)) *
                                LN(NULLIF(cc.cnt::float / NULLIF(cs.total, 0), 0))
                            ) / NULLIF(LN(GREATEST(cs.ch_count, 1)), 0))::numeric, 2
                        ) AS entropy
                    FROM (
                        SELECT customer_id, channel, COUNT(*) AS cnt
                        FROM customer_transactions_clean t
                        WHERE t.transaction_date::date > (%(d)s::date - INTERVAL '90 days')
                          AND t.transaction_date::date <= %(d)s::date
                        GROUP BY customer_id, channel
                    ) cc
                    JOIN (
                        SELECT customer_id,
                               COUNT(*) AS total,
                               COUNT(DISTINCT channel) AS ch_count
                        FROM customer_transactions_clean t
                        WHERE t.transaction_date::date > (%(d)s::date - INTERVAL '90 days')
                          AND t.transaction_date::date <= %(d)s::date
                        GROUP BY customer_id
                    ) cs ON cc.customer_id = cs.customer_id
                    GROUP BY cc.customer_id, cs.total, cs.ch_count
                ) agg
                WHERE cf.customer_id = agg.customer_id
                  AND cf.as_of_date = %(d)s::date
                """,
                {"d": as_of_date},
            )
            results["channel_entropy"] = cur.rowcount

            self._conn.commit()

        return results
