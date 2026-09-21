"""Train and export 14d, 30d, and 90d lifecycle forecast LightGBM models."""
from __future__ import annotations

import os
import sys
import pickle
import logging
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.preprocessing import LabelEncoder
from sklearn.calibration import CalibratedClassifierCV
import joblib

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_PRED_DIR = os.path.join(_PROJECT_ROOT, "services", "prediction-service")
if _PRED_DIR not in sys.path:
    sys.path.insert(0, _PRED_DIR)

from app.models.lifecycle_predictor import (
    FEATURES,
    HORIZONS,
    STAGE_ORDER,
    STAGES,
    _engineer,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("train_lifecycle")

MODEL_DIR = os.path.join(_PROJECT_ROOT, "models", "churn-lifecycle-prediction")
os.makedirs(MODEL_DIR, exist_ok=True)


def generate_synthetic_samples(n: int = 2000) -> list[dict]:
    rng = np.random.RandomState(42)
    rows = []
    for i in range(n):
        tenure = float(rng.uniform(10, 1500))
        days = float(rng.exponential(40))
        days = min(days, tenure)
        balance = float(rng.exponential(25000)) if rng.rand() > 0.1 else 0.0
        txn_30 = float(rng.poisson(8 if days < 30 else (2 if days < 90 else 0)))
        txn_90 = float(txn_30 + rng.poisson(15))

        rows.append({
            "customer_id": f"CUST{i+1:05d}",
            "tenure_days": tenure,
            "days_since_last_txn": days,
            "total_balance": balance,
            "txn_count_30d": txn_30,
            "txn_count_90d": txn_90,
        })
    return rows


def assign_stage(feat: dict, horizon: int) -> str:
    # Forward-projected days since last transaction at the horizon
    projected_days = feat["days_since_last_txn"] + horizon * 0.6
    balance = feat["total_balance"]
    tenure = feat["tenure_days"] + horizon

    if projected_days > 180 or (balance < 10.0 and projected_days > 90):
        return "CHURNED"
    if projected_days > 90:
        return "DORMANT"
    if projected_days > 30 or feat.get("balance_drain_risk", 0.0) == 1.0:
        return "AT_RISK"
    if tenure < 60:
        return "NEW"
    if feat["txn_velocity_ratio"] > 1.3 and feat["txn_count_30d"] >= 5:
        return "GROWING"
    return "ACTIVE"


def train_horizon(horizon: int):
    raw_rows = generate_synthetic_samples(3000)
    engineered = _engineer(raw_rows, horizon)

    feature_cols = list(FEATURES.get(horizon, (
        "tenure_days", "days_since_last_txn", "total_balance", "txn_count_30d",
        "txn_count_90d_weighted", "txn_velocity_ratio", "balance_per_txn",
        "is_zero_balance"
    )))

    X = np.array([[row[c] for c in feature_cols] for row in engineered], dtype=np.float32)
    y_labels = [assign_stage(row, horizon) for row in engineered]

    le = LabelEncoder()
    # Fit on the full sorted STAGES so all classes 0..5 are guaranteed
    le.fit(list(STAGE_ORDER))
    y = le.transform(y_labels)

    X_df = pd.DataFrame(X, columns=feature_cols)
    base_clf = lgb.LGBMClassifier(
        objective="multiclass",
        num_class=len(STAGE_ORDER),
        n_estimators=100,
        learning_rate=0.05,
        num_leaves=31,
        random_state=42,
        verbosity=-1,
        n_jobs=-1,
    )
    clf = CalibratedClassifierCV(estimator=base_clf, method='sigmoid', cv=5)
    clf.fit(X_df, y)



    # Save target encoder
    encoder_path = os.path.join(MODEL_DIR, f"label_encoder_{horizon}d.pkl")
    joblib.dump(le, encoder_path)

    # Save model artifact
    model_path = os.path.join(MODEL_DIR, f"lgbm_{horizon}d_model.pkl")
    bundle = {
        "model": clf,
        "feature_names": feature_cols,
        "target_encoder": le,
        "categorical_features": [],
    }
    joblib.dump(bundle, model_path)

    logger.info("Horizon %dd model & encoder saved successfully.", horizon)


def main():
    for h in HORIZONS:
        train_horizon(h)


if __name__ == "__main__":
    main()
