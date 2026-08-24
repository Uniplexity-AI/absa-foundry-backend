"""Controlled churn experiment — prove the pipeline learns behavioural churn.

Generates synthetic customers where churn is CAUSALLY linked to behaviour
(churned customers have a 90+ day transaction gap), computes a small feature
set, and trains XGBoost with customer-disjoint (GroupKFold + holdout) validation.

If the pipeline is sound, AUC should be high (~1.0 for this clean signal) —
demonstrating that the earlier ~0.5 AUC was caused by random labels, not by the
model or the training pipeline.

Usage:
    python scripts/controlled_churn_experiment.py
"""
from __future__ import annotations

import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.base import clone
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, train_test_split

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_synthetic_feature_store_data import (
    SyntheticDataGenerator,
    Configuration,
)

AS_OF = pd.Timestamp("2026-07-27")


def build_features(customers: pd.DataFrame, txns: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build a small point-in-time feature set + churn label + customer groups."""
    cust = customers.set_index("customer_id")
    t = txns.copy()
    t["txn_date"] = pd.to_datetime(t["transaction_date"])
    t = t[t["txn_date"] <= AS_OF]

    f30 = t[t["txn_date"] > AS_OF - pd.Timedelta(days=30)].groupby("customer_id").size().rename("txn_count_30d")
    f90 = t[t["txn_date"] > AS_OF - pd.Timedelta(days=90)].groupby("customer_id").size().rename("txn_count_90d")
    f180 = t[t["txn_date"] > AS_OF - pd.Timedelta(days=180)].groupby("customer_id").size().rename("txn_count_180d")
    amt90 = t[t["txn_date"] > AS_OF - pd.Timedelta(days=90)].groupby("customer_id")["amount"].sum().rename("total_amount_90d")

    X = pd.DataFrame({"txn_count_30d": f30, "txn_count_90d": f90,
                      "txn_count_180d": f180, "total_amount_90d": amt90}).fillna(0).reindex(cust.index)
    y = (cust["status"] == "Closed").astype(int).values
    groups = cust.index.values
    return X.values, y, groups


def main() -> None:
    print("=" * 70)
    print("CONTROLLED CHURN EXPERIMENT")
    print("=" * 70)

    gen = SyntheticDataGenerator(Configuration(customers=5000, as_of_date=date(2026, 7, 27), seed=42))
    tables = gen.build()
    customers, txns = tables["customers_clean"], tables["customer_transactions_clean"]

    # 1. Verify the behavioural signal exists
    last_txn = txns.groupby("customer_id")["transaction_date"].max()
    cust = customers.set_index("customer_id")
    cust["days_since_last"] = (AS_OF - pd.to_datetime(last_txn)).dt.days
    print("\n1. Behavioural signal (days_since_last_txn):")
    print(f"   Closed customers: mean={cust[cust.status=='Closed'].days_since_last.mean():.1f}, "
          f"min={cust[cust.status=='Closed'].days_since_last.min():.1f}")
    print(f"   Active customers: mean={cust[cust.status=='Active'].days_since_last.mean():.1f}, "
          f"max={cust[cust.status=='Active'].days_since_last.max():.1f}")

    X, y, groups = build_features(customers, txns)
    print(f"\n2. Features: {X.shape}, positives: {int(y.sum())} ({100*y.mean():.1f}%)")

    base_params = dict(
        objective="binary:logistic", eval_metric="auc",
        max_depth=4, learning_rate=0.05, n_estimators=50,
        scale_pos_weight=(len(y) - y.sum()) / max(y.sum(), 1),
        subsample=0.8, colsample_bytree=0.8, random_state=42,
    )

    # 3. GroupKFold (customer-disjoint) OOF
    gkf = GroupKFold(n_splits=5)
    oof = np.zeros(len(y))
    for tr, va in gkf.split(X, y, groups=groups):
        m = xgb.XGBClassifier(**base_params)
        m.fit(X[tr], y[tr])
        oof[va] = m.predict_proba(X[va])[:, 1]
    oof_auc = roc_auc_score(y, oof)

    # 4. Customer-disjoint holdout
    tr_cust, te_cust = train_test_split(np.unique(groups), test_size=0.2, random_state=42)
    tr_mask = np.isin(groups, tr_cust)
    te_mask = np.isin(groups, te_cust)
    m = xgb.XGBClassifier(**base_params)
    m.fit(X[tr_mask], y[tr_mask])
    holdout_auc = roc_auc_score(y[te_mask], m.predict_proba(X[te_mask])[:, 1])

    print("\n3. Results (customer-disjoint validation):")
    print(f"   5-fold GroupKFold OOF AUC = {oof_auc:.4f}")
    print(f"   Holdout AUC (20% disjoint customers) = {holdout_auc:.4f}")

    if oof_auc > 0.85:
        print("\nVERDICT: PIPELINE SOUND — the model recovers a known behavioural churn signal.")
        print("The earlier ~0.5 AUC was caused by random labels, not the model or pipeline.")
    else:
        print("\nVERDICT: UNEXPECTED — investigate the feature/label construction.")


if __name__ == "__main__":
    main()
