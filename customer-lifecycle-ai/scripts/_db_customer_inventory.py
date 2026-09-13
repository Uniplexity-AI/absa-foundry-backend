"""Temporary diagnostic: inventory every table that holds customer data.

Lists, for both the source (etl_validation) and target (etl_clean) databases:
  * tables whose NAME mentions customer
  * tables that have a customer_id COLUMN (regardless of name)

Used to size up the blast radius before any destructive reset.

Usage (from repo root):  python scripts/_db_customer_inventory.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2  # noqa: E402

from shared.config.settings import settings  # noqa: E402

DATABASES = [
    ("etl_clean (target)", settings.database_target_url_sync),
    ("etl_validation (source)", settings.database_url_sync),
]

QUERY = """
SELECT c.table_schema, c.table_name
  FROM information_schema.columns c
  JOIN information_schema.tables t
    ON t.table_schema = c.table_schema AND t.table_name = c.table_name
 WHERE t.table_type = 'BASE TABLE'
   AND c.table_schema NOT IN ('pg_catalog', 'information_schema')
   AND (c.column_name = 'customer_id' OR c.table_name ILIKE '%%customer%%')
 GROUP BY c.table_schema, c.table_name
 ORDER BY c.table_schema, c.table_name
"""


def main() -> int:
    for label, url in DATABASES:
        print(f"\n===== {label} =====")
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        try:
            cur.execute(QUERY)
            tables = cur.fetchall()
            if not tables:
                print("  (no customer tables found)")
            total = 0
            for schema, table in tables:
                cur.execute(f'SELECT count(*) FROM "{schema}"."{table}"')
                n = cur.fetchone()[0]
                total += n
                print(f"  {schema}.{table:<34} {n:>10,} rows")
            print(f"  {'TOTAL':<42} {total:>10,} rows")
        finally:
            cur.close()
            conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
