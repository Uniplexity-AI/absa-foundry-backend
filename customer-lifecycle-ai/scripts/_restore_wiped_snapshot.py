"""One-off repair for customer 000000222.

The 2026-07-13 feature snapshot the user entered (19:28:38) was destroyed by the
cleanup wipe at 19:32:48. Its values are still present in
backups/20260913_193248_etl_clean.sql (customer_features COPY block, line 1052).

Every app view queries the pilot snapshot date 2026-07-27, so the values are
re-applied to the 000000222 @ 2026-07-27 row that is actually served. Only
currently-NULL columns are filled, so nothing the user has since entered is
overwritten.

Usage:
    python scripts/_restore_wiped_snapshot.py --dry-run
    python scripts/_restore_wiped_snapshot.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2  # noqa: E402

from shared.config.settings import settings  # noqa: E402

CUSTOMER_ID = "000000222"
AS_OF_DATE = "2026-07-27"

#: Verbatim from the 2026-07-13 row in the pre-wipe dump. Columns the old row
#: left as NULL are omitted (they carry no information to restore).
VALUES: dict[str, object] = {
    "days_since_last_txn": 2000,
    "days_since_first_txn": 30,
    "txn_count_30d": 40,
    "txn_count_90d": 40,
    "txn_count_180d": 30,
    "txn_count_365d": 400,
    "avg_days_between_txn": 600.0,
    "total_amount_90d": 30000.0,
    "avg_amount_90d": 40.0,
    "dominant_channel": "MOBILE_APP",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(settings.database_target_url_sync)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT " + ", ".join(VALUES) + " FROM public.customer_features "
            "WHERE customer_id = %s AND as_of_date = %s",
            (CUSTOMER_ID, AS_OF_DATE),
        )
        row = cur.fetchone()
        if row is None:
            print(f"No snapshot for {CUSTOMER_ID} @ {AS_OF_DATE} — nothing to repair.")
            return 1

        before = dict(zip(VALUES, row))
        fill = {k: v for k, v in VALUES.items() if before[k] is None}

        print(f"{CUSTOMER_ID} @ {AS_OF_DATE}:")
        for col in VALUES:
            state = "empty -> fill" if before[col] is None else f"kept ({before[col]!r})"
            print(f"  {col:<24} {state}")

        if not fill:
            print("\nNothing empty; no change made.")
            return 0
        if args.dry_run:
            print(f"\n--dry-run: would fill {len(fill)} column(s).")
            return 0

        assignments = ", ".join(f"{col} = COALESCE({col}, %s)" for col in fill)
        cur.execute(
            f"UPDATE public.customer_features SET {assignments} "
            "WHERE customer_id = %s AND as_of_date = %s",
            (*fill.values(), CUSTOMER_ID, AS_OF_DATE),
        )
        conn.commit()
        print(f"\nUpdated {cur.rowcount} row(s), filled {len(fill)} column(s).")

        cur.execute(
            "SELECT " + ", ".join(VALUES) + " FROM public.customer_features "
            "WHERE customer_id = %s AND as_of_date = %s",
            (CUSTOMER_ID, AS_OF_DATE),
        )
        print("read back:", dict(zip(VALUES, cur.fetchone())))
    except Exception:
        conn.rollback()
        print("FAILED — rolled back.")
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
