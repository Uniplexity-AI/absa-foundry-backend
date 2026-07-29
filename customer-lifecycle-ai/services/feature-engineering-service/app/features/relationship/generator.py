"""Relationship Generator — Domain 5 of the Customer Feature Store.

Computes customer-bank relationship features: account status, products held,
loan presence, card portfolio, and digital engagement.

Unlocks 9 features across 4 clean tables:
- customers_clean:  rel_customer_status
- accounts_clean:   rel_accounts_active, rel_has_savings, rel_products_owned
- loans_clean:      rel_has_loan
- cards_clean:      rel_has_card, rel_card_count, rel_has_unactivated_card,
                    rel_card_expiring_30d, rel_card_types
- digital_engagement_clean: eng_login_count_30d, eng_digital_platform_preference,
                            eng_avg_session_duration_30d, eng_login_count_7d
"""

from __future__ import annotations

from datetime import date

import psycopg2


class RelationshipGenerator:
    """Generates relationship features from customers_clean, accounts_clean,
    loans_clean, cards_clean, and digital_engagement_clean."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def generate(self, as_of_date: date) -> dict:
        """Run all relationship, card, and engagement features.

        Stage 1: rel_customer_status from customers_clean
        Stage 2: Account features from accounts_clean
        Stage 3: Loan features from loans_clean
        Stage 4: Card features from cards_clean
        Stage 5: Engagement features from digital_engagement_clean
        """
        results = {}

        with self._conn.cursor() as cur:
            # ---- Stage 1: Customer status ----
            cur.execute(
                """
                UPDATE customer_features cf
                SET rel_customer_status = cc.status
                FROM (
                    SELECT DISTINCT ON (customer_id) *
                    FROM customers_clean
                    ORDER BY customer_id, loaded_at DESC
                ) cc
                WHERE RIGHT(cf.customer_id, 5) = RIGHT(cc.customer_id, 5)
                  AND cf.as_of_date = %(d)s::date
                """,
                {"d": as_of_date},
            )
            results["rel_status"] = cur.rowcount
            self._conn.commit()

            # ---- Stage 2: Account features ----
            try:
                cur.execute(
                    """
                    UPDATE customer_features cf
                    SET
                        rel_accounts_active = agg.active_count,
                        rel_has_savings     = agg.has_savings,
                        rel_products_owned  = agg.product_count
                    FROM (
                        SELECT
                            m.features_customer_id AS customer_id,
                            COUNT(*) FILTER (WHERE a.status = 'ACTIVE') AS active_count,
                            BOOL_OR(a.account_type = 'SAVINGS') AS has_savings,
                            COUNT(DISTINCT a.account_type) AS product_count
                        FROM accounts_clean a
                        JOIN customer_id_mapping m
                          ON m.source_customer_id = a.customer_id
                         AND m.source_table = 'accounts_clean'
                        GROUP BY m.features_customer_id
                    ) agg
                    WHERE cf.customer_id = agg.customer_id
                      AND cf.as_of_date = %(d)s::date
                    """,
                    {"d": as_of_date},
                )
                results["rel_accounts"] = cur.rowcount
                self._conn.commit()
            except Exception as e:
                self._conn.rollback()
                results["rel_accounts"] = f"skipped: {e}"

            # ---- Stage 3: Loan features ----
            try:
                cur.execute(
                    """
                    UPDATE customer_features cf
                    SET rel_has_loan = agg.has_loan
                    FROM (
                        SELECT
                            m.features_customer_id AS customer_id,
                            BOOL_OR(l.status = 'ACTIVE') AS has_loan
                        FROM loans_clean l
                        JOIN customer_id_mapping m
                          ON m.source_customer_id = l.customer_id
                         AND m.source_table = 'loans_clean'
                        GROUP BY m.features_customer_id
                    ) agg
                    WHERE cf.customer_id = agg.customer_id
                      AND cf.as_of_date = %(d)s::date
                    """,
                    {"d": as_of_date},
                )
                results["rel_loans"] = cur.rowcount
                self._conn.commit()
            except Exception as e:
                self._conn.rollback()
                results["rel_loans"] = f"skipped: {e}"

            # ---- Stage 4: Card features ----
            try:
                cur.execute(
                    """
                    UPDATE customer_features cf
                    SET
                        rel_has_card           = agg.has_card,
                        rel_card_count         = agg.card_count,
                        rel_has_unactivated_card = agg.has_unactivated,
                        rel_card_expiring_30d  = agg.expiring_30d,
                        rel_card_types         = agg.card_types
                    FROM (
                        SELECT
                            m.features_customer_id AS customer_id,
                            BOOL_OR(c.status = 'ACTIVE') AS has_card,
                            COUNT(*) AS card_count,
                            BOOL_OR(c.status = 'INACTIVE' AND c.issued_date IS NOT NULL)
                                AS has_unactivated,
                            COUNT(*) FILTER (
                                WHERE c.expiry_date BETWEEN %(d)s::date AND (%(d)s::date + INTERVAL '30 days')
                            ) AS expiring_30d,
                            COUNT(DISTINCT c.card_type) AS card_types
                        FROM cards_clean c
                        JOIN customer_id_mapping m
                          ON m.source_customer_id = c.customer_id
                         AND m.source_table = 'cards_clean'
                        GROUP BY m.features_customer_id
                    ) agg
                    WHERE cf.customer_id = agg.customer_id
                      AND cf.as_of_date = %(d)s::date
                    """,
                    {"d": as_of_date},
                )
                results["rel_cards"] = cur.rowcount
                self._conn.commit()
            except Exception as e:
                self._conn.rollback()
                results["rel_cards"] = f"skipped: {e}"

            # ---- Stage 5: Digital engagement features ----
            try:
                cur.execute(
                    """
                    UPDATE customer_features cf
                    SET
                        eng_login_count_7d  = agg.login_7d,
                        eng_login_count_30d = agg.login_30d,
                        eng_digital_platform_preference = agg.dominant_platform,
                        eng_avg_session_duration_30d = agg.avg_duration
                    FROM (
                        SELECT
                            m.features_customer_id AS customer_id,
                            COUNT(*) FILTER (
                                WHERE de.login_date > (%(d)s::date - INTERVAL '7 days')
                                  AND de.login_date <= %(d)s::date
                            ) AS login_7d,
                            COUNT(*) FILTER (
                                WHERE de.login_date > (%(d)s::date - INTERVAL '30 days')
                                  AND de.login_date <= %(d)s::date
                            ) AS login_30d,
                            (
                                SELECT platform FROM (
                                    SELECT de2.platform,
                                           ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS rn
                                    FROM digital_engagement_clean de2
                                    JOIN customer_id_mapping m2
                                      ON m2.source_customer_id = de2.customer_id
                                     AND m2.source_table = 'digital_engagement_clean'
                                    WHERE m2.features_customer_id = m.features_customer_id
                                      AND de2.login_date > (%(d)s::date - INTERVAL '30 days')
                                      AND de2.login_date <= %(d)s::date
                                    GROUP BY de2.platform
                                ) s WHERE rn = 1
                            ) AS dominant_platform,
                            AVG(de.session_duration_seconds) FILTER (
                                WHERE de.login_date > (%(d)s::date - INTERVAL '30 days')
                                  AND de.login_date <= %(d)s::date
                            ) AS avg_duration
                        FROM digital_engagement_clean de
                        JOIN customer_id_mapping m
                          ON m.source_customer_id = de.customer_id
                         AND m.source_table = 'digital_engagement_clean'
                        WHERE de.login_date <= %(d)s::date
                        GROUP BY m.features_customer_id
                    ) agg
                    WHERE cf.customer_id = agg.customer_id
                      AND cf.as_of_date = %(d)s::date
                    """,
                    {"d": as_of_date},
                )
                results["eng_digital"] = cur.rowcount
                self._conn.commit()
            except Exception as e:
                self._conn.rollback()
                results["eng_digital"] = f"skipped: {e}"

        return results
