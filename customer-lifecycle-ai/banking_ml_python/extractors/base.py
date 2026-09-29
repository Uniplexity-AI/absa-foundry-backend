"""Base utilities for extractors."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from dateutil.relativedelta import relativedelta

from config.db import read_sql
from config.settings import FEATURE_HISTORY_MONTHS, OUTPUT_DIR, SQL_DIR


def load_sql(filename: str) -> str:
    path = SQL_DIR / filename
    return path.read_text()


def month_start(d: date) -> date:
    return d.replace(day=1)


def history_start_for(snapshot: date, months: int = FEATURE_HISTORY_MONTHS) -> date:
    return month_start(snapshot - relativedelta(months=months))


def save_dataset(df: pd.DataFrame, model: str, mode: str, snapshot: str) -> Path:
    out_dir = OUTPUT_DIR / model / mode
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{model}_{mode}_{snapshot}.parquet"
    df.to_parquet(path, index=False)
    csv_path = out_dir / f"{model}_{mode}_{snapshot}.csv"
    df.to_csv(csv_path, index=False)
    print(f"  Wrote {len(df):,} rows x {len(df.columns)} cols -> {path}")
    return path


def run_query(sql_file: str, params: dict) -> pd.DataFrame:
    sql = load_sql(sql_file)
    print(f"  Running {sql_file} with params {params}")
    return read_sql(sql, params)
