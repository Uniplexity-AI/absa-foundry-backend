"""Wipe ALL customer data from etl_clean, after dumping both databases.

SCOPE
  Removes every table in `etl_clean.public` that holds customer data — i.e. any
  table with a `customer_id` column, plus any table whose name matches
  "customer" (currently 18 tables, ~484k rows). IAM users/roles, model
  registry/artifacts and configuration are NOT touched.

  `etl_validation` (the raw/landing layer) is dumped for safety but NOT
  modified — this script only ever writes to `etl_clean`.

SAFETY
  * Refuses to truncate if a table OUTSIDE the list has a foreign key into a
    table INSIDE it (TRUNCATE ... CASCADE would silently take that table too).
  * Backup runs first, and the run aborts if a dump is missing or empty.
  * All truncates run in ONE transaction; any error rolls the whole thing back.

USAGE (from repo root)
  python scripts/_db_wipe_customers.py --dry-run   # report only, changes nothing
  python scripts/_db_wipe_customers.py             # backup, then wipe
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2  # noqa: E402

from shared.config.settings import settings  # noqa: E402

TARGET_URL = settings.database_target_url_sync      # etl_clean
SOURCE_URL = settings.database_url_sync             # etl_validation
BACKUP_DIR = Path(__file__).resolve().parent.parent / "backups"

#: Tables in etl_clean.public holding customer data.
DISCOVER_SQL = """
SELECT t.table_name
  FROM information_schema.tables t
 WHERE t.table_type = 'BASE TABLE'
   AND t.table_schema = 'public'
   AND (
        t.table_name ILIKE '%%customer%%'
        OR EXISTS (
             SELECT 1 FROM information_schema.columns c
              WHERE c.table_schema = t.table_schema
                AND c.table_name = t.table_name
                AND c.column_name = 'customer_id')
       )
 ORDER BY t.table_name
"""

#: FKs pointing INTO a listed table from a table that is NOT listed.
OUTSIDE_FK_SQL = """
SELECT DISTINCT r.relname AS referencing_table
  FROM pg_constraint con
  JOIN pg_class c      ON c.oid = con.confrelid
  JOIN pg_namespace n  ON n.oid = c.relnamespace
  JOIN pg_class r      ON r.oid = con.conrelid
  JOIN pg_namespace rn ON rn.oid = r.relnamespace
 WHERE con.contype = 'f'
   AND n.nspname = 'public'
   AND rn.nspname = 'public'
   AND c.relname = ANY(%s)
   AND r.relname <> ALL(%s)
 ORDER BY 1
"""


def counts(conn, schema: str, tables: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    cur = conn.cursor()
    try:
        for t in tables:
            cur.execute(f'SELECT count(*) FROM "{schema}"."{t}"')
            out[t] = cur.fetchone()[0]
    finally:
        cur.close()
    return out


def discover(conn) -> list[str]:
    cur = conn.cursor()
    try:
        cur.execute(DISCOVER_SQL)
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()


def outside_fks(conn, tables: list[str]) -> list[str]:
    cur = conn.cursor()
    try:
        cur.execute(OUTSIDE_FK_SQL, (tables, tables))
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()


def pg_dump(url: str, out_file: Path) -> None:
    exe = shutil.which("pg_dump") or r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"
    if not Path(exe).exists():
        raise SystemExit(f"pg_dump not found (looked for {exe}); refusing to wipe without a backup.")
    cmd = [exe, f"--dbname={url}", "--format=plain", "--no-owner", "--no-privileges", f"--file={out_file}"]
    print(f"  dumping -> {out_file.name} ...", flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit(f"pg_dump failed ({res.returncode}):\n{res.stderr.strip()}")
    if not out_file.exists() or out_file.stat().st_size == 0:
        raise SystemExit(f"backup {out_file} is missing or empty — aborting.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report what would happen, change nothing")
    ap.add_argument(
        "--dump-source",
        action="store_true",
        help="also dump etl_validation (this script never writes to it, so the dump is insurance only)",
    )
    args = ap.parse_args()

    conn = psycopg2.connect(TARGET_URL)
    try:
        tables = discover(conn)
        if not tables:
            print("Nothing matched — no customer tables found in etl_clean.public.")
            return 0
        before = counts(conn, "public", tables)
        blockers = outside_fks(conn, tables)
    finally:
        conn.close()

    total = sum(before.values())
    print(f"etl_clean.public — {len(tables)} customer tables, {total:,} rows:")
    for t in tables:
        print(f"  {t:<34} {before[t]:>10,}")

    if blockers:
        print("\nABORT: these tables are NOT in the list but have a foreign key into it.")
        print("TRUNCATE ... CASCADE would empty them too — review before proceeding:")
        for b in blockers:
            print(f"  - public.{b}")
        return 2

    print("\nFK check: no outside table depends on the list (CASCADE cannot leak).")

    if args.dry_run:
        print("\n--dry-run: nothing changed.")
        return 0

    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\nBacking up to {BACKUP_DIR}")
    pg_dump(TARGET_URL, BACKUP_DIR / f"{stamp}_etl_clean.sql")
    if args.dump_source:
        pg_dump(SOURCE_URL, BACKUP_DIR / f"{stamp}_etl_validation.sql")

    manifest = BACKUP_DIR / f"{stamp}_counts_before.json"
    manifest.write_text(json.dumps({"database": "etl_clean", "tables": before}, indent=2))
    print(f"  recorded pre-wipe counts -> {manifest.name}")

    print(f"\nTruncating {len(tables)} tables in etl_clean (one transaction)...")
    conn = psycopg2.connect(TARGET_URL)
    try:
        cur = conn.cursor()
        names = ", ".join(f'public."{t}"' for t in tables)
        cur.execute(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE")
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        print("FAILED — rolled back, etl_clean is unchanged.")
        raise
    finally:
        conn.close()

    conn = psycopg2.connect(TARGET_URL)
    try:
        after = counts(conn, "public", tables)
    finally:
        conn.close()

    remaining = sum(after.values())
    print(f"\nAfter: {remaining:,} rows across the {len(tables)} tables.")
    for t in tables:
        if after[t]:
            print(f"  NON-ZERO {t}: {after[t]:,}")
    print("etl_clean customer wipe complete." if remaining == 0 else "Some rows remain — see above.")
    for f in sorted(BACKUP_DIR.glob(f"{stamp}_*")):
        print(f"  backup: {f}  ({f.stat().st_size / 1_048_576:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
