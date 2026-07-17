"""
ETL Verification Script — Compare engine output against ground truth.

Queries both source (etl_validation) and target (etl_clean) databases
to verify the ETL pipeline correctly rejects dirty rows and produces
a clean dataset matching ground-truth expectations.

Usage:
    python verify.py
    python verify.py --verbose
"""

from __future__ import annotations

import argparse
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from shared.config.settings import settings
import psycopg2


# ---------------------------------------------------------------------------
# Ground truth expected counts (from etl_validation_customers.csv data_issue column)
# ---------------------------------------------------------------------------
GROUND_TRUTH = {
    "duplicate": 350,
    "missing_branch": 50,
    "bad_date": 50,
    "invalid_channel": 50,
    "missing_account": 50,
    "negative_amount": 50,
    "missing_amount": 50,
    "missing_customer": 50,
    "future_date": 50,
    "invalid_currency": 50,
}
GROUND_TRUTH_TOTAL = sum(GROUND_TRUTH.values())  # 800


def verify(verbose: bool = False) -> dict:
    """Run full verification and return a result dict."""
    result = {"pass": True, "checks": []}

    # ---- Source DB: Ground Truth ----
    src = psycopg2.connect(settings.database_url_sync)
    sc = src.cursor()
    sc.execute(
        "SELECT data_issue, COUNT(*) AS cnt FROM customer_transactions "
        "WHERE data_issue IS NOT NULL GROUP BY data_issue ORDER BY cnt DESC"
    )
    gt_rows = {r[0]: r[1] for r in sc.fetchall()}
    sc.execute("SELECT COUNT(*) FROM customer_transactions WHERE data_issue IS NOT NULL")
    gt_total = sc.fetchone()[0]
    src.close()

    print("=" * 60)
    print("  ETL VERIFICATION — Ground Truth vs Engine Output")
    print("=" * 60)

    # ---- Target DB: Engine Output ----
    tgt = psycopg2.connect(settings.database_target_url_sync)
    tc = tgt.cursor()

    tc.execute(
        "SELECT rejection_reason, COUNT(*) AS cnt FROM customer_transactions_rejected "
        "GROUP BY rejection_reason ORDER BY cnt DESC"
    )
    rejection_rows = {r[0]: r[1] for r in tc.fetchall()}

    tc.execute("SELECT COUNT(*) FROM customer_transactions_rejected")
    total_rejected = tc.fetchone()[0]
    tc.execute("SELECT COUNT(*) FROM customer_transactions_clean")
    total_clean = tc.fetchone()[0]
    grand_total = total_rejected + total_clean

    tc.execute(
        "SELECT quality_score, duplicates_detected, rows_skipped, rows_received, "
        "rows_valid, rows_rejected, rows_loaded FROM etl.etl_audit ORDER BY id DESC LIMIT 1"
    )
    audit = tc.fetchone()

    # Check for co-flagged CUR+DUP rows (should be 0 after fix)
    tc.execute(
        "SELECT COUNT(*) FROM customer_transactions_rejected "
        "WHERE rejection_reason LIKE '%DUP%' AND rejection_reason LIKE '%CUR%'"
    )
    co_flagged = tc.fetchone()[0]

    # Check for rescued constraint violations
    tc.execute(
        "SELECT COUNT(*) FROM customer_transactions_rejected "
        "WHERE rejection_reason LIKE 'db_constraint%'"
    )
    rescued = tc.fetchone()[0]

    tgt.close()

    # ---- Print rejection reasons ----
    print("\n--- Rejection Reasons (etl_clean) ---")
    for reason, count in sorted(rejection_rows.items(), key=lambda x: -x[1]):
        print(f"  {reason:55s}: {count:>6,}")

    # ---- High-level checks ----
    print("\n--- High-Level Checks ---")
    checks = []

    # Check 1: Total rejected
    check1 = total_rejected == GROUND_TRUTH_TOTAL
    checks.append(("Total rejected = 800", total_rejected, GROUND_TRUTH_TOTAL, check1))

    # Check 2: Grand total
    check2 = grand_total == 70472
    checks.append(("Grand total = 70,472", grand_total, 70472, check2))

    # Check 3: DUP-001 count
    dup_count = rejection_rows.get("DUP-001", 0)
    check3 = dup_count == GROUND_TRUTH["duplicate"]
    checks.append(("DUP-001 = 350", dup_count, GROUND_TRUTH["duplicate"], check3))

    # Check 4: Co-flagged CUR+DUP
    check4 = co_flagged == 0
    checks.append(("Co-flagged CUR+DUP = 0", co_flagged, 0, check4))

    # Check 5: Rescued constraint violations
    check5 = rescued == 0
    checks.append(("Rescued from constraints = 0", rescued, 0, check5))

    # Check 6: Audit skipped
    skipped = audit[2] if audit else -1
    check6 = skipped == 0
    checks.append(("Audit rows_skipped = 0", skipped, 0, check6))

    for label, actual, expected, passed in checks:
        status = "✅" if passed else "❌"
        print(f"  {status} {label}: got {actual}, expected {expected}")
        if not passed:
            result["pass"] = False

    # ---- Per-rule checks ----
    if verbose:
        print("\n--- Per-Rule Checks ---")
        rule_map = {
            "duplicate": ("DUP-001", 350),
            "invalid_currency": ("BUSINESS-CUR-001", 50),
            "invalid_channel": ("BUSINESS-CHN-001", 50),
            "bad_date": ("BUSINESS-DATE-001", 50),
            "future_date": ("BUSINESS-DATE-002", 50),
            "negative_amount": ("BUSINESS-AMT-001", 50),
            "missing_amount": ("MANDATORY-AMOUNT", 50),
            "missing_customer": ("MANDATORY-CUSTOMER_ID", 50),
            "missing_account": ("MANDATORY-ACCOUNT_ID", 50),
            "missing_branch": ("MANDATORY-BRANCH_CODE", 50),
        }
        for gt_label, (rule_id, expected_count) in rule_map.items():
            actual_count = sum(
                count for reason, count in rejection_rows.items()
                if rule_id in reason and "db_constraint" not in reason
            )
            match = actual_count == expected_count
            status = "✅" if match else "❌"
            print(f"  {status} {gt_label:20s} → {rule_id:25s}: {actual_count} (expected {expected_count})")
            if not match:
                result["pass"] = False

    # ---- Summary ----
    print(f"\n--- Summary ---")
    print(f"  Source dirty rows (ground truth): {gt_total}")
    print(f"  Engine rejected rows:             {total_rejected}")
    print(f"  Engine clean rows:                {total_clean}")
    print(f"  Grand total:                      {grand_total} / 70,472")
    print(f"  Missing:                          {70472 - grand_total}")
    if audit:
        print(f"  Quality score:                    {audit[0]:.1f}%")
        print(f"  Audit duplicates:                 {audit[1]}")
        print(f"  Audit rows_skipped:               {audit[2]}")

    overall = "✅ ALL CHECKS PASSED" if result["pass"] else "❌ SOME CHECKS FAILED"
    print(f"\n  {overall}")
    print("=" * 60)

    result["checks"] = checks
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL verification against ground truth")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-rule breakdown")
    args = parser.parse_args()

    result = verify(verbose=args.verbose)
    if not result["pass"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
