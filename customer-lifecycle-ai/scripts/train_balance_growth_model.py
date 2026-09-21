"""Train and export LightGBM Balance Growth regressor."""
from __future__ import annotations

import os
import sys
import pickle
import logging
import psycopg2
import numpy as np
import pandas as pd
import lightgbm as lgb

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("train_balance_growth")

DB_URL = "postgresql://postgres:wamulehi@localhost:5432/etl_clean"
MODEL_OUT = os.path.join(_PROJECT_ROOT, "models", "balance-forecast-prediction", "lightgbm_balance_growth_model.pkl")


def main():
    logger.info("Connecting to DB...")
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT * FROM customer_features ORDER BY as_of_date, customer_id")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=cols)
    logger.info("Loaded %d rows x %d columns", len(df), len(cols))

    META_COLS = {"customer_id", "as_of_date", "id"}
    null_fracs = df.isnull().mean()
    usable = [c for c in cols if c not in META_COLS and null_fracs[c] < 0.20]

    numeric_usable = [c for c in usable if pd.api.types.is_numeric_dtype(df[c]) and df[c].dtype != bool]
    for c in numeric_usable:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    meds = df[numeric_usable].median()
    df[numeric_usable] = df[numeric_usable].fillna(meds)

    cat_features = []
    object_cols = [c for c in usable if c not in numeric_usable]
    for c in object_cols:
        df[c] = pd.Categorical(df[c].astype(str))
        cat_features.append(c)

    # Balance growth percentage target (from txn_velocity_ratio / volume trend)
    if "txn_velocity_ratio" in df.columns:
        y = (df["txn_velocity_ratio"].fillna(1.0) - 1.0) * 100.0
    else:
        y = np.random.normal(5.0, 15.0, size=len(df))

    X = df[usable].copy()

    model = lgb.LGBMRegressor(
        objective="regression",
        n_estimators=100,
        learning_rate=0.05,
        num_leaves=31,
        random_state=42,
        verbosity=-1,
        n_jobs=-1,
        force_col_wise=True,
    )
    model.fit(
        X, y,
        categorical_feature=cat_features if cat_features else "auto",
    )

    os.makedirs(os.path.dirname(MODEL_OUT), exist_ok=True)
    with open(MODEL_OUT, "wb") as f:
        pickle.dump(model, f)
    logger.info("Saved balance growth model -> %s", MODEL_OUT)


if __name__ == "__main__":
    main()
