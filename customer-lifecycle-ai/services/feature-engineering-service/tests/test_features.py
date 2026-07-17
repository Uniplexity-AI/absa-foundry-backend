"""
Feature Engineering Service — Regression Tests.

Point-in-time correctness, upsert idempotency, edge cases.
Uses hand-crafted fixture data with exact expected values.
"""

from __future__ import annotations

from conftest import (
    EXPECTED_A_DEC31, EXPECTED_A_JUN30, EXPECTED_B_DEC31, EXPECTED_D_DEC31,
    compute, get_features, get_latest, insert_fixture,
)


class TestPointInTime:
    """Point-in-time correctness: transactions after as_of_date must not affect features."""

    def test_dec31_excludes_jan05_transaction(self):
        """Transaction on 2025-01-05 must NOT affect features as of 2024-12-31."""
        insert_fixture()
        compute("2024-12-31")
        f = get_features("CUST-TEST-A", "2024-12-31")
        assert f is not None, "CUST-TEST-A should have features as of 2024-12-31"
        for key, expected in EXPECTED_A_DEC31.items():
            actual = f[key]
            assert actual == expected, (
                f"{key}: expected {expected}, got {actual}"
            )

    def test_jun30_has_different_values_than_dec31(self):
        """Features as of 2024-06-30 differ from 2024-12-31 because windows shift."""
        insert_fixture()
        compute("2024-06-30")
        f = get_features("CUST-TEST-A", "2024-06-30")
        assert f is not None
        for key, expected in EXPECTED_A_JUN30.items():
            actual = f[key]
            assert actual == expected, (
                f"{key}: expected {expected}, got {actual}"
            )

    def test_dec31_values_are_not_cumulative(self):
        """txn_count_180d is a trailing window, not cumulative — can be smaller at later date."""
        insert_fixture()
        compute("2024-06-30")
        compute("2024-12-31")
        f_jun = get_features("CUST-TEST-A", "2024-06-30")
        f_dec = get_features("CUST-TEST-A", "2024-12-31")
        # Jun has 3 txns in 180d (Jan-Jun), Dec has 1 (Jul-Dec only — T1-T3 fell out)
        assert f_jun["txn_count_180d"] == 3
        assert f_dec["txn_count_180d"] == 1
        assert f_dec["txn_count_180d"] < f_jun["txn_count_180d"], (
            "Trailing window should shrink as older txns fall out"
        )


class TestUpsertIdempotency:
    """Computing the same as_of_date twice must produce identical results."""

    def test_row_count_identical(self):
        insert_fixture()
        compute("2024-12-31")
        import psycopg2
        from shared.config.settings import settings
        conn = psycopg2.connect(settings.database_target_url_sync)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM customer_features WHERE as_of_date = '2024-12-31'")
        count1 = cur.fetchone()[0]
        conn.close()

        compute("2024-12-31")
        conn = psycopg2.connect(settings.database_target_url_sync)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM customer_features WHERE as_of_date = '2024-12-31'")
        count2 = cur.fetchone()[0]
        conn.close()

        assert count1 == count2, f"Upsert changed row count: {count1} -> {count2}"

    def test_values_identical_after_recompute(self):
        insert_fixture()
        compute("2024-12-31")
        f1 = get_features("CUST-TEST-A", "2024-12-31")
        compute("2024-12-31")
        f2 = get_features("CUST-TEST-A", "2024-12-31")
        for key in EXPECTED_A_DEC31:
            assert f1[key] == f2[key], f"{key} drifted: {f1[key]} -> {f2[key]}"


class TestDivisionByZeroGuard:
    """amount_growth_ratio must return NULL when denominator is zero, not crash."""

    def test_equal_90d_and_180d_returns_null(self):
        """Customer D: total_90d == total_180d == 200. Ratio must be NULL."""
        insert_fixture()
        compute("2024-12-31")
        f = get_features("CUST-TEST-D", "2024-12-31")
        assert f is not None
        assert f["amount_growth_ratio"] is None, (
            f"Expected NULL for 200/0, got {f['amount_growth_ratio']}"
        )
        assert f["total_amount_90d"] == 200.00
        assert f["total_amount_180d"] == 200.00


class TestSingleTransactionCustomer:
    """A customer with exactly one transaction must compute without error."""

    def test_single_txn_computes_without_error(self):
        insert_fixture()
        compute("2024-12-31")
        f = get_features("CUST-TEST-B", "2024-12-31")
        assert f is not None
        for key, expected in EXPECTED_B_DEC31.items():
            actual = f[key]
            assert actual == expected, f"{key}: expected {expected}, got {actual}"


class TestZeroTransactionCustomer:
    """Customer with no transactions before as_of_date must be excluded entirely."""

    def test_future_only_customer_excluded(self):
        """CUST-TEST-C has transactions only after as_of_date — must not appear."""
        insert_fixture()
        compute("2024-12-31")
        f = get_features("CUST-TEST-C", "2024-12-31")
        assert f is None, (
            "CUST-TEST-C should be excluded (no transactions before as_of_date)"
        )


class TestNonExistentSnapshot:
    """Looking up a date that was never computed must return None/404."""

    def test_uncomputed_date_returns_none(self):
        insert_fixture()
        compute("2024-12-31")
        f = get_features("CUST-TEST-A", "2024-01-01")  # never computed
        assert f is None, "Uncomputed date must return None, not fall back"


class TestLatestEndpoint:
    """GET /latest must return the snapshot with max as_of_date, not most-recently-inserted."""

    def test_latest_returns_max_as_of_date_not_last_inserted(self):
        """Backfill earlier date after later date — latest must still be the max date."""
        insert_fixture()
        # Insert in reverse: later date first, then earlier
        compute("2024-12-31")
        compute("2024-06-30")  # backfill — inserted after Dec but earlier date

        latest = get_latest("CUST-TEST-A")
        assert latest is not None
        assert latest["as_of_date"].isoformat() == "2024-12-31", (
            f"Latest should be 2024-12-31 (max as_of_date), got {latest['as_of_date']}"
        )
        # Also verify the values match Dec 31 expected
        assert latest["txn_count_30d"] == EXPECTED_A_DEC31["txn_count_30d"]
