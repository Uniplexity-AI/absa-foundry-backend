"""CLV dataset: shared + CLV features + labels (from DBeaver 03_clv_dataset.sql)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from config.settings import CLV_FORWARD_MONTHS
from extractors.base import history_start_for, month_start, run_query, save_dataset
from extractors.shared import extract_shared


def build_clv(snapshot_month: date, mode: str = "training") -> pd.DataFrame:
    snap = month_start(snapshot_month)
    shared = extract_shared(snap)

    params = {
        "snapshot_month": snap.isoformat(),
        "history_start": history_start_for(snap).isoformat(),
        "clv_forward_months": CLV_FORWARD_MONTHS,
    }
    clv_extra = run_query("02_clv_features_labels.sql", params)

    df = shared.merge(clv_extra, on=["customer_id", "snapshot_month"], how="left")

    if mode == "scoring":
        target_cols = [c for c in df.columns if c.startswith("target_")]
        df = df.drop(columns=target_cols, errors="ignore")

    # Derived features (same as original ETL)
    if "monetary_12m" in df.columns and "frequency_12m" in df.columns:
        df["avg_transaction_value_12m"] = df["monetary_12m"] / df["frequency_12m"].replace(
            0, pd.NA
        )

    if "fee_income_12m" in df.columns and "avg_monthly_nii_12m" in df.columns:
        df["total_revenue_proxy_12m"] = (
            df["fee_income_12m"].fillna(0) + df["avg_monthly_nii_12m"].fillna(0) * 12
        )

    save_dataset(df, "clv", mode, snap.strftime("%Y%m"))
    return df
