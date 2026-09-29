"""Balance forecast dataset (from DBeaver 06_balance_dataset.sql)."""
from __future__ import annotations

from datetime import date

import pandas as pd
from dateutil.relativedelta import relativedelta

from config.settings import BALANCE_FORWARD_DAYS, FEATURE_HISTORY_MONTHS, LARGE_OUTFLOW_THRESHOLD
from extractors.base import run_query, save_dataset


def build_balance(as_of_date: date, mode: str = "training") -> pd.DataFrame:
    hist_start = as_of_date - relativedelta(months=FEATURE_HISTORY_MONTHS)
    params = {
        "as_of_date": as_of_date.isoformat(),
        "history_start": hist_start.isoformat(),
        "balance_forward_days": BALANCE_FORWARD_DAYS,
        "large_outflow_threshold": LARGE_OUTFLOW_THRESHOLD,
    }
    df = run_query("05_balance_features_labels.sql", params)

    if mode == "scoring":
        target_cols = [c for c in df.columns if c.startswith("target_")]
        df = df.drop(columns=target_cols, errors="ignore")

    save_dataset(df, "balance", mode, as_of_date.strftime("%Y%m%d"))
    return df
