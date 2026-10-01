"""Train and export LightGBM Balance Growth regressor."""
from __future__ import annotations

import os
import sys
import pickle
import logging
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error, r2_score

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from banking_ml_python.data_loader import load_training_data

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("train_balance_growth")

MODEL_OUT = os.path.join(_PROJECT_ROOT, "models", "balance-forecast-prediction", "lightgbm_balance_growth_model.pkl")

def walk_forward_split(df):
    # Use as_of_date for balance model
    dates = sorted(df['as_of_date'].unique())
    for i in range(1, len(dates)):
        train_dates = dates[:i]
        test_date = dates[i]
        
        train_idx = df.index[df['as_of_date'].isin(train_dates)]
        test_idx = df.index[df['as_of_date'] == test_date]
        
        yield train_idx, test_idx, test_date

def main():
    logger.info("Loading training data for balance model...")
    df = load_training_data('balance', target_columns=['target_dab_30d'])
    if df.empty:
        logger.error("No training data found for balance.")
        sys.exit(1)

    META_COLS = {"customer_id", "as_of_date", "id", "snapshot_month", "target_dab_30d", "target_dab_60d", "target_dab_90d"}
    
    # Filter numeric features only for now
    feature_cols = [c for c in df.columns if c not in META_COLS and pd.api.types.is_numeric_dtype(df[c])]
    
    logger.info(f"Using {len(feature_cols)} numeric features.")
    
    # Fill NAs
    df[feature_cols] = df[feature_cols].fillna(0)
    
    X = df[feature_cols]
    y = df["target_dab_30d"]

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
    
    # Walk-forward validation
    for train_idx, test_idx, test_date in walk_forward_split(df):
        X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
        X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]
        
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred) if len(y_test) > 1 else float('nan')
        logger.info(f"Fold {test_date}: MAE={mae:.2f}, R2={r2:.4f}")

    logger.info("Training final balance growth model on all data.")
    model.fit(X, y)

    os.makedirs(os.path.dirname(MODEL_OUT), exist_ok=True)
    with open(MODEL_OUT, "wb") as f:
        pickle.dump({'model': model, 'features': feature_cols}, f)
    logger.info("Saved balance growth model -> %s", MODEL_OUT)


if __name__ == "__main__":
    main()
