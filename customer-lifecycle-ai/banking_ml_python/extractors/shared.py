"""Shared feature foundation extractor (from DBeaver 02_shared_features.sql)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from extractors.base import history_start_for, month_start, run_query


def extract_shared(snapshot_month: date) -> pd.DataFrame:
    """
    Build shared customer features as of snapshot_month (first of month).
    Point-in-time: only uses data <= end of snapshot_month.
    """
    snap = month_start(snapshot_month)
    params = {
        "snapshot_month": snap.isoformat(),
        "history_start": history_start_for(snap).isoformat(),
    }
    return run_query("01_shared_features.sql", params)
