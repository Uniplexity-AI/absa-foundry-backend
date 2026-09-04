"""Truncate every downstream pipeline table in `etl_clean` (safe full reset).

Used by the pilot bootstrap before re-loading the synthetic dataset. Only tables
that exist are truncated (each with CASCADE), so it is safe on a first run too.

Usage (from repo root):
    python scripts/pilot_reset_clean.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2  # noqa: E402

from shared.config.settings import settings  # noqa: E402

# Downstream order is not critical because every TRUNCATE uses CASCADE.
TABLES = [
    "customer_states",
    "state_transitions",
    "customer_features",
    "customer_id_mapping",
    "pilot_action_log",
    "pilot_customer_state",
    "customer_transactions_clean",
    "customers_clean",
    "accounts_clean",
    "loans_clean",
    "cards_clean",
    "digital_engagement_clean",
    "demographics_clean",
]


def main() -> int:
    conn = psycopg2.connect(settings.database_target_url_sync)
    cur = conn.cursor()
    try:
        for table in TABLES:
            cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
            if cur.fetchone()[0] is None:
                print(f"skip {table} (not present)")
                continue
            cur.execute(f'TRUNCATE TABLE public."{table}" RESTART IDENTITY CASCADE')
            print(f"truncated {table}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    print("\netl_clean reset complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
