"""Run the FULL feature pipeline for one or more as-of dates.

Canonical entry point: runs Phase-1 SQL (`FeatureRepository.compute_batch`)
plus all domain generators (profile/behaviour/financial/channel/temporal/risk/
relationship) via `FeaturePipeline.run(as_of_date)`, writing rows into
`etl_clean.public.customer_features`.

Also (re)builds the identity `customer_id_mapping` (uniform CUST00001… format),
which the relationship generator joins on. Idempotent per date.

Usage (from repo root):
    python scripts/run_full_pipeline_all_dates.py                          # 07-17, 07-22, 07-27
    python scripts/run_full_pipeline_all_dates.py 2026-07-27               # single date
    python scripts/run_full_pipeline_all_dates.py 2026-07-17 2026-07-27    # specific dates
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

_PROJ = Path(__file__).resolve().parent.parent
os.chdir(_PROJ)
sys.path.insert(0, str(_PROJ))
sys.path.insert(0, str(_PROJ / "services" / "feature-engineering-service"))

import psycopg2  # noqa: E402

from app.pipelines.pipeline import FeaturePipeline  # noqa: E402
from app.repository.repository import FeatureRepository  # noqa: E402

DEFAULT_DATES = ["2026-07-17", "2026-07-22", "2026-07-27"]


def build_identity_mapping() -> None:
    """Populate customer_id_mapping as an identity join on customers_clean."""
    repo = FeatureRepository()
    conn = psycopg2.connect(repo._conn_str)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO customer_id_mapping (source_table, source_customer_id, features_customer_id)
            SELECT 'customers_clean', customer_id, customer_id FROM customers_clean
            ON CONFLICT DO NOTHING
            """
        )
        conn.commit()
        print(f"customer_id_mapping: {cur.rowcount} rows inserted (identity)")
    finally:
        cur.close()
        conn.close()


def main() -> int:
    dates = [a for a in sys.argv[1:]] or DEFAULT_DATES
    build_identity_mapping()
    repo = FeatureRepository()
    ok = True
    for d in dates:
        print(f"\n=== feature pipeline as_of {d} ===")
        try:
            result = FeaturePipeline(repo).run(date.fromisoformat(d))
            status = result.get("status", "?")
            stages = result.get("stages")
            quality = result.get("quality")
            print(f"{d}: status={status}")
            print(f"  stages : {stages}")
            print(f"  quality: {quality}")
            if status != "COMPLETED":
                ok = False
        except Exception as exc:  # noqa: BLE001
            print(f"{d}: FAILED — {exc!r}")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
