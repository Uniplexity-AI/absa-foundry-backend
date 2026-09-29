"""Churn / dormancy dataset (from DBeaver 04_churn_dataset.sql).

Label definition (updated):
  DORMANT = >= dormancy_threshold_days consecutive days without qualifying activity.
  churn_30d / churn_90d = 1 if the customer reaches that threshold within the
  forward window (or would, given the inactivity clock and future resets).
  Already-dormant customers at snapshot receive label 0 (prospective prediction only).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from config.settings import (
    CHURN_HORIZON_DAYS,
    CHURN_SHORT_HORIZON_DAYS,
    DORMANCY_THRESHOLD_DAYS,
    LARGE_OUTFLOW_THRESHOLD,
)
from extractors.base import history_start_for, month_start, run_query, save_dataset
from extractors.shared import extract_shared


def build_churn(snapshot_month: date, mode: str = "training") -> pd.DataFrame:
    snap = month_start(snapshot_month)
    shared = extract_shared(snap)

    params = {
        "snapshot_month": snap.isoformat(),
        "history_start": history_start_for(snap).isoformat(),
        "churn_short_horizon_days": CHURN_SHORT_HORIZON_DAYS,
        "churn_horizon_days": CHURN_HORIZON_DAYS,
        "dormancy_threshold_days": DORMANCY_THRESHOLD_DAYS,
        "large_outflow_threshold": LARGE_OUTFLOW_THRESHOLD,
    }
    churn_extra = run_query("03_churn_features_labels.sql", params)

    # Prefer shared's snapshot_date / recency if both present
    churn_extra = churn_extra.drop(
        columns=[c for c in ("snapshot_date", "snapshot_month", "recency_days") if c in churn_extra.columns],
        errors="ignore",
    )
    df = shared.merge(churn_extra, on="customer_id", how="left")

    if mode == "scoring":
        label_cols = [
            c
            for c in df.columns
            if c.startswith("churn_") or c in ("days_to_dormancy", "future_txn_count_90d")
        ]
        # Keep days_to_dormancy and lifecycle_status as features; drop only supervised labels
        label_cols = [c for c in label_cols if c.startswith("churn_")]
        df = df.drop(columns=label_cols, errors="ignore")

    save_dataset(df, "churn", mode, snap.strftime("%Y%m"))
    return df
