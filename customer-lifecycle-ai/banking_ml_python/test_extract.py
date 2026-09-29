#!/usr/bin/env python3
"""
Smoke test for Banking ML Python ETL.

Runs each SQL stage limited to N rows (default 5) so you can verify:
  - DB connectivity
  - SQL parses and executes
  - expected columns exist
  - shared → model merge works

Usage:
  export PGHOST=... PGPORT=5432 PGDATABASE=absa_dw PGUSER=... PGPASSWORD=...
  python test_extract.py
  python test_extract.py --limit 5 --snapshot 2024-06-01
  python test_extract.py --limit 3 --models shared,clv --mode training

Does NOT write production parquet files under output/ (writes tiny samples to output/test/).
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
from dateutil.relativedelta import relativedelta

from config.db import get_connection_params, get_conn, read_sql
from config.settings import (
    BALANCE_FORWARD_DAYS,
    CHURN_HORIZON_DAYS,
    CHURN_SHORT_HORIZON_DAYS,
    CLV_FORWARD_MONTHS,
    DORMANCY_THRESHOLD_DAYS,
    FEATURE_HISTORY_MONTHS,
    LARGE_OUTFLOW_THRESHOLD,
    OUTPUT_DIR,
    SQL_DIR,
)
from extractors.base import history_start_for, load_sql, month_start


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def strip_trailing_semicolon(sql: str) -> str:
    return sql.rstrip().rstrip(";").rstrip()


def run_limited(sql_file: str, params: dict, limit: int) -> pd.DataFrame:
    """Execute SQL wrapped so the final result is capped at `limit` rows."""
    raw = load_sql(sql_file)
    body = strip_trailing_semicolon(raw)
    limited_sql = f"SELECT * FROM (\n{body}\n) AS _test_q LIMIT {int(limit)}"
    print(f"  Running {sql_file} (LIMIT {limit}) params={params}")
    return read_sql(limited_sql, params)


def test_connection() -> bool:
    print("\n[1] Connection test")
    params = get_connection_params()
    safe = {k: ("***" if k == "password" else v) for k, v in params.items()}
    print(f"  Connecting with {safe}")
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok, current_database() AS db, current_user AS usr")
                row = cur.fetchone()
                print(f"  OK  → db={row[1]} user={row[2]}")
        return True
    except Exception as e:
        print(f"  FAIL → {e}")
        traceback.print_exc()
        return False


def test_source_tables() -> bool:
    """Quick existence check for key source tables (non-fatal warnings)."""
    print("\n[2] Source table existence (informational)")
    tables = [
        "a_africa_zam_base_customer",
        "a_africa_zam_base_customers_new",
        "a_africa_zam_base_customer_employment_daily_zm",
        "a_brains_trans_zam_base_entries_zm",
        "ebox_loan_details",
        "s_caas_sparrow_zam_base_crdrep",
    ]
    ok = True
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for t in tables:
                    cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_name = %s
                        )
                        """,
                        (t,),
                    )
                    exists = cur.fetchone()[0]
                    status = "found" if exists else "MISSING"
                    if not exists:
                        ok = False
                    print(f"  {status:7}  {t}")
    except Exception as e:
        print(f"  Could not check tables: {e}")
        return False
    return ok


def summarize(df: pd.DataFrame, name: str) -> None:
    print(f"  → {name}: {len(df)} rows × {len(df.columns)} cols")
    print(f"    columns: {list(df.columns)[:12]}{' ...' if len(df.columns) > 12 else ''}")
    if len(df) > 0:
        print(df.head(min(3, len(df))).to_string(index=False))
    else:
        print("    (empty result)")


def test_shared(snap: date, limit: int) -> pd.DataFrame | None:
    print("\n[3] Shared features")
    params = {
        "snapshot_month": snap.isoformat(),
        "history_start": history_start_for(snap).isoformat(),
    }
    try:
        df = run_limited("01_shared_features.sql", params, limit)
        summarize(df, "shared")
        required = {"customer_id", "snapshot_month", "recency_days", "frequency_90d"}
        missing = required - set(df.columns)
        if missing:
            print(f"  WARN missing columns: {missing}")
        return df
    except Exception as e:
        print(f"  FAIL → {e}")
        traceback.print_exc()
        return None


def test_clv(snap: date, shared: pd.DataFrame, limit: int, mode: str) -> bool:
    print("\n[4] CLV extras + merge")
    params = {
        "snapshot_month": snap.isoformat(),
        "history_start": history_start_for(snap).isoformat(),
        "clv_forward_months": CLV_FORWARD_MONTHS,
    }
    try:
        extra = run_limited("02_clv_features_labels.sql", params, limit)
        summarize(extra, "clv_extra")
        df = shared.merge(extra, on=["customer_id", "snapshot_month"], how="left")
        if mode == "scoring":
            targets = [c for c in df.columns if c.startswith("target_")]
            df = df.drop(columns=targets, errors="ignore")
        summarize(df, f"clv merged ({mode})")
        return True
    except Exception as e:
        print(f"  FAIL → {e}")
        traceback.print_exc()
        return False


def test_churn(snap: date, shared: pd.DataFrame, limit: int, mode: str) -> bool:
    print("\n[5] Churn extras + merge")
    params = {
        "snapshot_month": snap.isoformat(),
        "history_start": history_start_for(snap).isoformat(),
        "churn_short_horizon_days": CHURN_SHORT_HORIZON_DAYS,
        "churn_horizon_days": CHURN_HORIZON_DAYS,
        "dormancy_threshold_days": DORMANCY_THRESHOLD_DAYS,
        "large_outflow_threshold": LARGE_OUTFLOW_THRESHOLD,
    }
    try:
        extra = run_limited("03_churn_features_labels.sql", params, limit)
        summarize(extra, "churn_extra")
        drop_cols = [c for c in ("snapshot_date", "snapshot_month", "recency_days") if c in extra.columns]
        extra = extra.drop(columns=drop_cols, errors="ignore")
        df = shared.merge(extra, on="customer_id", how="left")
        if mode == "scoring":
            labels = [c for c in df.columns if c.startswith("churn_")]
            df = df.drop(columns=labels, errors="ignore")
        summarize(df, f"churn merged ({mode})")
        return True
    except Exception as e:
        print(f"  FAIL → {e}")
        traceback.print_exc()
        return False


def test_lifecycle(snap: date, shared: pd.DataFrame, limit: int, mode: str) -> bool:
    print("\n[6] Lifecycle extras + merge")
    params = {
        "snapshot_month": snap.isoformat(),
        "history_start": history_start_for(snap).isoformat(),
    }
    try:
        extra = run_limited("04_lifecycle_features.sql", params, limit)
        summarize(extra, "lifecycle_extra")
        drop_cols = [c for c in ("snapshot_month", "snapshot_date") if c in extra.columns]
        extra = extra.drop(columns=drop_cols, errors="ignore")
        df = shared.merge(extra, on="customer_id", how="left")

        if mode == "training":

            def heuristic_stage(row):
                rec = row.get("recency_days")
                freq = row.get("frequency_90d") or 0
                prods = row.get("num_active_products") or 0
                if rec is None or (isinstance(rec, float) and pd.isna(rec)) or rec > 180:
                    return "Dormancy"
                if prods <= 1 and freq < 5:
                    return "Acquisition"
                if freq >= 20 and prods >= 3:
                    return "Growth"
                return "Maturity"

            df["lifecycle_stage_label"] = df.apply(heuristic_stage, axis=1)

        summarize(df, f"lifecycle merged ({mode})")
        return True
    except Exception as e:
        print(f"  FAIL → {e}")
        traceback.print_exc()
        return False


def test_balance(as_of: date, limit: int, mode: str) -> bool:
    print("\n[7] Balance")
    hist_start = as_of - relativedelta(months=FEATURE_HISTORY_MONTHS)
    params = {
        "as_of_date": as_of.isoformat(),
        "history_start": hist_start.isoformat(),
        "balance_forward_days": BALANCE_FORWARD_DAYS,
        "large_outflow_threshold": LARGE_OUTFLOW_THRESHOLD,
    }
    try:
        df = run_limited("05_balance_features_labels.sql", params, limit)
        if mode == "scoring":
            targets = [c for c in df.columns if c.startswith("target_")]
            df = df.drop(columns=targets, errors="ignore")
        summarize(df, f"balance ({mode})")
        return True
    except Exception as e:
        print(f"  FAIL → {e}")
        traceback.print_exc()
        return False


def save_sample(df: pd.DataFrame, name: str) -> None:
    out = OUTPUT_DIR / "test"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}_sample.csv"
    df.to_csv(path, index=False)
    print(f"  Sample saved → {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test Banking ML Python ETL (limited rows)")
    parser.add_argument("--limit", type=int, default=5, help="Max rows per query (default 5)")
    parser.add_argument("--snapshot", type=str, default="2024-06-01", help="Snapshot month YYYY-MM-DD")
    parser.add_argument("--as-of", type=str, default=None, help="Balance as-of date (default = snapshot)")
    parser.add_argument(
        "--mode",
        choices=["training", "scoring"],
        default="training",
        help="training keeps labels; scoring drops them",
    )
    parser.add_argument(
        "--models",
        default="all",
        help="Comma list: shared,clv,lifecycle,churn,balance or 'all'",
    )
    parser.add_argument(
        "--skip-table-check",
        action="store_true",
        help="Skip information_schema table existence checks",
    )
    args = parser.parse_args()

    models = (
        ["shared", "clv", "lifecycle", "churn", "balance"]
        if args.models.strip().lower() == "all"
        else [m.strip().lower() for m in args.models.split(",")]
    )

    snap = month_start(parse_date(args.snapshot))
    as_of = parse_date(args.as_of) if args.as_of else snap
    limit = max(1, args.limit)

    print("=" * 60)
    print("Banking ML ETL — SMOKE TEST")
    print(f"  mode={args.mode}  limit={limit}  snapshot={snap}  as_of={as_of}")
    print(f"  models={models}")
    print(f"  sql_dir={SQL_DIR}")
    print("=" * 60)

    results: dict[str, bool] = {}

    results["connection"] = test_connection()
    if not results["connection"]:
        print("\n*** Cannot continue without a working DB connection. ***")
        print("Set PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD and retry.")
        sys.exit(1)

    if not args.skip_table_check:
        results["tables"] = test_source_tables()

    shared: pd.DataFrame | None = None
    if any(m in models for m in ("shared", "clv", "lifecycle", "churn")):
        shared = test_shared(snap, limit)
        results["shared"] = shared is not None and len(shared.columns) > 0
        if shared is not None and len(shared) > 0:
            save_sample(shared, "shared")

    if shared is None and any(m in models for m in ("clv", "lifecycle", "churn")):
        print("\n*** Shared failed — skipping model merge tests that depend on it. ***")
        for m in ("clv", "lifecycle", "churn"):
            if m in models:
                results[m] = False
    else:
        if "clv" in models and shared is not None:
            results["clv"] = test_clv(snap, shared, limit, args.mode)
        if "churn" in models and shared is not None:
            results["churn"] = test_churn(snap, shared, limit, args.mode)
        if "lifecycle" in models and shared is not None:
            results["lifecycle"] = test_lifecycle(snap, shared, limit, args.mode)

    if "balance" in models:
        results["balance"] = test_balance(as_of, limit, args.mode)

    print("\n" + "=" * 60)
    print("RESULTS")
    all_ok = True
    for name, ok in results.items():
        flag = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{flag}] {name}")
    print("=" * 60)

    if all_ok:
        print("All selected checks passed.")
        sys.exit(0)
    else:
        print("Some checks failed — see traceback above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
