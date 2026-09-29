"""Lifecycle dataset: shared + lifecycle features (from DBeaver 05_lifecycle_dataset.sql)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from extractors.base import history_start_for, month_start, run_query, save_dataset
from extractors.shared import extract_shared


def build_lifecycle(snapshot_month: date, mode: str = "training") -> pd.DataFrame:
    snap = month_start(snapshot_month)
    shared = extract_shared(snap)

    params = {
        "snapshot_month": snap.isoformat(),
        "history_start": history_start_for(snap).isoformat(),
    }
    life_extra = run_query("04_lifecycle_features.sql", params)

    life_extra = life_extra.drop(
        columns=[c for c in ("snapshot_month", "snapshot_date") if c in life_extra.columns],
        errors="ignore",
    )
    df = shared.merge(life_extra, on="customer_id", how="left")

    # Optional heuristic stage label for evaluation only (not used as training target)
    def heuristic_stage(row):
        rec = row.get("recency_days")
        freq = row.get("frequency_90d") or 0
        prods = row.get("num_active_products") or 0
        if rec is None or rec > 180:
            return "Dormancy"
        if prods <= 1 and freq < 5:
            return "Acquisition"
        if freq >= 20 and prods >= 3:
            return "Growth"
        return "Maturity"

    if mode == "training":
        df["lifecycle_stage_label"] = df.apply(heuristic_stage, axis=1)

    # Feature store column alignment
    if "direct_deposit_flag" in df.columns and "salary_flag" not in df.columns:
        df["salary_flag"] = df["direct_deposit_flag"].fillna(0).astype(int)
    if "direct_deposit_consistency_flag" in df.columns and "salary_consistency_3m" not in df.columns:
        df["salary_consistency_3m"] = df["direct_deposit_consistency_flag"].fillna(0).astype(int)
    if "activity_change_pct_90d" in df.columns and "activity_change_flag" not in df.columns:
        df["activity_change_flag"] = df["activity_change_pct_90d"].apply(
            lambda x: 1 if pd.notna(x) and abs(x) > 0.5 else 0
        )
    if "avg_salary_amount" not in df.columns:
        df["avg_salary_amount"] = None
    if "txn_count_12m" not in df.columns:
        df["txn_count_12m"] = df.get("frequency_12m", 0)
    if "distinct_channels_90d" not in df.columns:
        df["distinct_channels_90d"] = 1

    save_dataset(df, "lifecycle", mode, snap.strftime("%Y%m"))
    return df
