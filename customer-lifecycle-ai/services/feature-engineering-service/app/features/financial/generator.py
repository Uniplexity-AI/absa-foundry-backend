"""
Financial Generator — Domain 3 of the Customer Feature Store.

Computes money movement features: credits, debits, income estimation,
salary detection, and cashflow patterns.

All stages use optimized FROM-subquery approach (single scan per stage,
no correlated subqueries).
"""

from __future__ import annotations

from datetime import date

import psycopg2


class FinancialGenerator:
    """Generates financial features from transaction data."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def generate(self, as_of_date: date) -> dict:
        """Run all financial features in optimized SQL.

        Stage 1: Credit/debit/median + income growth (single 180-day scan).
        Stage 2: Salary consistency (single 90-day scan with monthly grouping).
        """
        results = {}

        with self._conn.cursor() as cur:
            # Stage 1: Credit/debit totals + median + income growth (single pass)
            cur.execute(
                """
                UPDATE customer_features cf
                SET
                    fin_total_credit_90d = COALESCE(agg.credit_90d, 0),
                    fin_total_debit_90d  = COALESCE(agg.debit_90d, 0),
                    fin_median_txn_amount_90d = agg.median_amount,
                    fin_income_growth = CASE
                        WHEN agg.prev_credits > 0
                        THEN ROUND((COALESCE(agg.credit_90d, 0)::float
                              / NULLIF(agg.prev_credits, 0)::float)::numeric, 2)
                        ELSE NULL
                    END
                FROM (
                    SELECT
                        t.customer_id,
                        SUM(t.amount) FILTER (
                            WHERE t.transaction_type = 'CREDIT'
                              AND t.transaction_date::date > (%(d)s::date - INTERVAL '90 days')
                        ) AS credit_90d,
                        SUM(t.amount) FILTER (
                            WHERE t.transaction_type = 'DEBIT'
                              AND t.transaction_date::date > (%(d)s::date - INTERVAL '90 days')
                        ) AS debit_90d,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY t.amount)
                            FILTER (
                                WHERE t.transaction_date::date > (%(d)s::date - INTERVAL '90 days')
                            ) AS median_amount,
                        SUM(t.amount) FILTER (
                            WHERE t.transaction_type = 'CREDIT'
                              AND t.transaction_date::date > (%(d)s::date - INTERVAL '180 days')
                              AND t.transaction_date::date <= (%(d)s::date - INTERVAL '90 days')
                        ) AS prev_credits
                    FROM customer_transactions_clean t
                    WHERE t.transaction_date::date > (%(d)s::date - INTERVAL '180 days')
                      AND t.transaction_date::date <= %(d)s::date
                    GROUP BY t.customer_id
                ) agg
                WHERE cf.customer_id = agg.customer_id
                  AND cf.as_of_date = %(d)s::date
                """,
                {"d": as_of_date},
            )
            results["credit_debit_growth"] = cur.rowcount

            # Stage 2: Salary consistency (FROM-subquery with monthly grouping)
            cur.execute(
                """
                UPDATE customer_features cf
                SET fin_salary_consistency = agg.salary_cv
                FROM (
                    SELECT
                        ms.customer_id,
                        CASE
                            WHEN AVG(ms.monthly) > 0
                            THEN ROUND((STDDEV(ms.monthly)::float
                                  / NULLIF(AVG(ms.monthly), 0)::float)::numeric, 2)
                            ELSE NULL
                        END AS salary_cv
                    FROM (
                        SELECT
                            t.customer_id,
                            DATE_TRUNC('month', t.transaction_date) AS month,
                            SUM(t.amount) AS monthly
                        FROM customer_transactions_clean t
                        WHERE t.transaction_date::date > (%(d)s::date - INTERVAL '90 days')
                          AND t.transaction_date::date <= %(d)s::date
                          AND t.transaction_type = 'CREDIT'
                          AND t.amount >= 500
                        GROUP BY t.customer_id, DATE_TRUNC('month', t.transaction_date)
                    ) ms
                    GROUP BY ms.customer_id
                ) agg
                WHERE cf.customer_id = agg.customer_id
                  AND cf.as_of_date = %(d)s::date
                """,
                {"d": as_of_date},
            )
            results["salary_consistency"] = cur.rowcount

            self._conn.commit()

        return results
