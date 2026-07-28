"""Relationship Generator — Domain 5 of the Customer Feature Store.

Computes customer-bank relationship features: account status, products held.
Currently computes 1 of 5 features — rel_customer_status from customers_clean.
The other 4 require accounts/loans tables not yet available.
"""

from __future__ import annotations

from datetime import date

import psycopg2


class RelationshipGenerator:
    """Generates relationship features from customers_clean."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def generate(self, as_of_date: date) -> dict:
        """Copy rel_customer_status from customers_clean.status.

        Uses the same RIGHT(id,5) join + DISTINCT ON dedup pattern
        as the profile generator.
        """
        results = {}

        with self._conn.cursor() as cur:
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

        return results
