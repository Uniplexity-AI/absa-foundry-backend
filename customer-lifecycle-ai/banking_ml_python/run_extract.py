#!/usr/bin/env python3
"""
Banking ML ETL — Python runner

Builds training and scoring datasets for CLV, Lifecycle, Churn, and Balance.
Logic converted from banking_ml_dbeaver_sql_updated; architecture mirrors banking_ml_etl.

Usage:
  export PGHOST=... PGPORT=5432 PGDATABASE=absa_dw PGUSER=... PGPASSWORD=...
  pip install -r requirements.txt

  # All models, training, snapshot June 2024
  python run_extract.py --mode training --models all --snapshot 2024-06-01

  # Churn scoring only
  python run_extract.py --mode scoring --models churn --snapshot 2024-09-01

  # Balance (daily as-of)
  python run_extract.py --mode training --models balance --as-of 2024-06-30
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

# Allow running from package root without installing
sys.path.insert(0, str(Path(__file__).resolve().parent))

from extractors.balance import build_balance
from extractors.churn import build_churn
from extractors.clv import build_clv
from extractors.lifecycle import build_lifecycle


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build banking ML training/scoring datasets (Python ETL)"
    )
    parser.add_argument(
        "--mode",
        choices=["training", "scoring"],
        required=True,
        help="training = include labels/targets; scoring = features only",
    )
    parser.add_argument(
        "--models",
        default="all",
        help="Comma list: clv,lifecycle,churn,balance or 'all'",
    )
    parser.add_argument(
        "--snapshot",
        type=str,
        default=None,
        help="Snapshot month (YYYY-MM-DD, first of month) for CLV/Lifecycle/Churn",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="As-of date (YYYY-MM-DD) for Balance model",
    )
    args = parser.parse_args()

    models = (
        ["clv", "lifecycle", "churn", "balance"]
        if args.models.strip().lower() == "all"
        else [m.strip().lower() for m in args.models.split(",")]
    )

    print("=" * 60)
    print(f"Banking ML Python ETL | mode={args.mode} | models={models}")
    print("=" * 60)

    if any(m in models for m in ("clv", "lifecycle", "churn")):
        if not args.snapshot:
            raise SystemExit("--snapshot YYYY-MM-DD required for clv/lifecycle/churn")
        snap = parse_date(args.snapshot)

    if "balance" in models:
        as_of = (
            parse_date(args.as_of)
            if args.as_of
            else (parse_date(args.snapshot) if args.snapshot else None)
        )
        if not as_of:
            raise SystemExit("--as-of or --snapshot required for balance")

    results = {}

    if "clv" in models:
        print("\n[CLV]")
        results["clv"] = build_clv(snap, mode=args.mode)

    if "lifecycle" in models:
        print("\n[Lifecycle]")
        results["lifecycle"] = build_lifecycle(snap, mode=args.mode)

    if "churn" in models:
        print("\n[Churn]")
        results["churn"] = build_churn(snap, mode=args.mode)

    if "balance" in models:
        print("\n[Balance]")
        results["balance"] = build_balance(as_of, mode=args.mode)

    print("\n" + "=" * 60)
    print("Done. Datasets written under output/<model>/<mode>/")
    for name, df in results.items():
        print(f"  {name}: {len(df):,} rows × {len(df.columns)} columns")
    print("=" * 60)


if __name__ == "__main__":
    main()
