"""
Customer Profile Generator — Domain 1 of the Customer Feature Store.

Computes slowly-changing customer attributes from customers_clean.
All features are point-in-time correct (as_of_date constrained).

ID Mapping: customer_features uses CUST##### IDs while customers_clean uses
C01###### IDs. We join via RIGHT(id, 5) which maps CUST00001→C01000001.
We also deduplicate customers_clean via DISTINCT ON (multiple batch loads).

Bank market segment (authoritative, single source of truth):
  * customers_clean.market_segment_code  — raw bank value (preserved)
  * customer_features.market_segment     — deterministic label resolved here via
    shared/constants/market_segments.py (NO SQL CASE — single implementation).
  * Existing customer_segment (= customer_type) semantics are left untouched
    for backward compatibility (see docs/ml/market-segment-integration.md).
"""

from __future__ import annotations

from datetime import date

import psycopg2

from shared.constants.market_segments import resolve_market_segment


class CustomerProfileGenerator:
    """Generates customer-level profile features from customers_clean."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def generate(self, as_of_date: date) -> dict:
        """Update customer_features with profile attributes.

        Args:
            as_of_date: Compute features as of this date.

        Returns:
            Dict with row counts per stage.
        """
        results = {}

        with self._conn.cursor() as cur:
            # Stage 1: Copy base attributes from customers_clean
            # Uses DISTINCT ON to deduplicate (3 batch loads = 3 rows per customer)
            # Uses RIGHT(id, 5) to match CUST##### with C01###### IDs
            cur.execute(
                """
                UPDATE customer_features cf
                SET
                    customer_segment       = cc.customer_type,
                    market_segment_code    = cc.market_segment_code,
                    customer_tenure_days   = (%(d)s::date - cc.activation_date::date),
                    age_years              = EXTRACT(YEAR FROM AGE(%(d)s::date, cc.date_of_birth::date)),
                    onboarding_channel     = cc.onboarding_channel,
                    prof_primary_branch    = cc.branch_code
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
            results["profile_base"] = cur.rowcount

            # Stage 1b: Resolve the deterministic market_segment label.
            # Done in Python from the single authoritative mapping module
            # (shared/constants/market_segments.py). Unknown/NULL codes → 'Other'
            # but the original code is preserved in market_segment_code above.
            cur.execute(
                """
                SELECT cc.customer_id, cc.market_segment_code
                FROM (
                    SELECT DISTINCT ON (customer_id) customer_id, market_segment_code
                    FROM customers_clean
                    WHERE market_segment_code IS NOT NULL
                    ORDER BY customer_id, loaded_at DESC
                ) cc
                WHERE EXISTS (
                    SELECT 1 FROM customer_features cf
                    WHERE RIGHT(cf.customer_id, 5) = RIGHT(cc.customer_id, 5)
                      AND cf.as_of_date = %(d)s::date
                )
                """,
                {"d": as_of_date},
            )
            rows = cur.fetchall()
            labelled = 0
            for customer_clean_id, code in rows:
                label = resolve_market_segment(code)
                cur.execute(
                    """
                    UPDATE customer_features
                    SET market_segment = %(label)s
                    WHERE RIGHT(customer_id, 5) = RIGHT(%(cid)s, 5)
                      AND as_of_date = %(d)s::date
                    """,
                    {"label": label, "cid": customer_clean_id, "d": as_of_date},
                )
                labelled += cur.rowcount
            results["market_segment_labelled"] = labelled

            # Stage 2: Derived features (age band)
            cur.execute(
                """
                UPDATE customer_features
                SET prof_age_band = CASE
                    WHEN age_years < 18 THEN '<18'
                    WHEN age_years BETWEEN 18 AND 25 THEN '18-25'
                    WHEN age_years BETWEEN 26 AND 35 THEN '26-35'
                    WHEN age_years BETWEEN 36 AND 50 THEN '36-50'
                    WHEN age_years BETWEEN 51 AND 65 THEN '51-65'
                    WHEN age_years >= 65 THEN '65+'
                END
                WHERE as_of_date = %(d)s::date
                  AND age_years IS NOT NULL
                """,
                {"d": as_of_date},
            )
            results["profile_derived"] = cur.rowcount

            self._conn.commit()

        return results
