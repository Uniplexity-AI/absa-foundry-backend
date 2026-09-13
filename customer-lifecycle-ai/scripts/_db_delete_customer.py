"""Delete ONE customer's rows from every customer table in etl_clean.

Targeted alternative to `_db_wipe_customers.py`: removes a single customer id
(exact match only — no patterns) so test rows can be cleaned up without touching
anything else in the database.

Usage (from repo root):
    python scripts/_db_delete_customer.py CUST-BROWSER-002
    python scripts/_db_delete_customer.py CUST-BROWSER-002 --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2  # noqa: E402

from shared.config.settings import settings  # noqa: E402

TARGET_URL = settings.database_target_url_sync

#: Tables that actually key on customer_id. Deliberately narrower than the wipe
#: tool's discovery (which also name-matches "customer%") because this deletes by
#: customer_id, and `customer_id_mapping` for one is keyed differently.
DISCOVER_SQL = """
SELECT c.table_name
  FROM information_schema.columns c
  JOIN information_schema.tables t
    ON t.table_schema = c.table_schema AND t.table_name = c.table_name
 WHERE c.table_schema = 'public'
   AND t.table_type = 'BASE TABLE'
   AND c.column_name = 'customer_id'
 ORDER BY c.table_name
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("customer_id", help="exact customer id to delete (no wildcards)")
    ap.add_argument("--dry-run", action="store_true", help="report what would be deleted")
    args = ap.parse_args()

    if any(ch in args.customer_id for ch in "%_*"):
        raise SystemExit("Refusing: pass an exact customer id, not a pattern.")

    conn = psycopg2.connect(TARGET_URL)
    try:
        cur = conn.cursor()
        cur.execute(DISCOVER_SQL)
        tables = [r[0] for r in cur.fetchall()]

        plan: list[tuple[str, int]] = []
        for table in tables:
            cur.execute(
                f'SELECT count(*) FROM public."{table}" WHERE customer_id = %s',
                (args.customer_id,),
            )
            n = cur.fetchone()[0]
            if n:
                plan.append((table, n))

        if not plan:
            print(f"No rows found for {args.customer_id!r} in any of the {len(tables)} customer tables.")
            return 0

        print(f"{args.customer_id!r} appears in:")
        for table, n in plan:
            print(f"  {table:<34} {n:>6}")

        if args.dry_run:
            print("\n--dry-run: nothing deleted.")
            return 0

        for table, _ in plan:
            cur.execute(
                f'DELETE FROM public."{table}" WHERE customer_id = %s',
                (args.customer_id,),
            )
            print(f"deleted {cur.rowcount} from {table}")
        conn.commit()
        print(f"\n{args.customer_id!r} removed.")
    except Exception:
        conn.rollback()
        print("FAILED — rolled back, nothing changed.")
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
