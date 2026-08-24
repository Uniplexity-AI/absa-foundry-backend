import psycopg2
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import os
import sys

def run_analysis():
    # Connect to the DB
    load_dotenv(".env")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        db_url = "postgresql://postgres:wamulehi@localhost:5432/etl_clean"
    else:
        # the generator script connects to target_url_sync which is usually etl_clean
        db_url = "postgresql://postgres:wamulehi@localhost:5432/etl_clean"
        
    print(f"Connecting to {db_url}")
    try:
        conn = psycopg2.connect(db_url)
    except Exception as e:
        print(f"Failed to connect: {e}")
        return
    
    # 1. Investigate Temporal Data Generation
    print("--- 1. Snapshot Statistics ---")
    df = pd.read_sql("SELECT * FROM customer_features", conn)
    
    if df.empty:
        print("No data in customer_features.")
        return

    dates = sorted(df['as_of_date'].unique())
    print(f"Snapshots found: {dates}")
    
    features = [
        'avg_days_between_txn', 'behav_txn_count_7d', 'engagement_score',
        'temp_weekend_txn_ratio_90d', 'days_since_last_txn'
    ]
    
    for f in features:
        if f not in df.columns:
            continue
        print(f"\nFeature: {f}")
        for d in dates:
            sub = df[df['as_of_date'] == d][f]
            print(f"  {d}: mean={sub.mean():.2f}, median={sub.median():.2f}, nulls={sub.isnull().sum()}, max={sub.max()}")
            
    # 2. Investigate PSI = 9.51
    print("\n--- 2. PSI Distribution Check ---")
    if len(dates) >= 2:
        train_df = df[df['as_of_date'] == dates[0]]
        holdout_df = df[df['as_of_date'] == dates[-1]]
        
        def _compute_psi(train, test, bins=10):
            train = np.asarray(train, dtype=float)
            test = np.asarray(test, dtype=float)
            train = train[np.isfinite(train)]
            test = test[np.isfinite(test)]
            if len(train) == 0 or len(test) == 0:
                return 0.0
            all_vals = np.concatenate([train, test])
            if np.ptp(all_vals) == 0:
                return 0.0
            edges = np.unique(np.percentile(all_vals, np.linspace(0, 100, bins + 1)))
            if len(edges) < 2:
                return 0.0
            train_hist, _ = np.histogram(train, bins=edges)
            test_hist, _ = np.histogram(test, bins=edges)
            eps = 1e-6
            train_pct = (train_hist + eps) / (train_hist.sum() + eps * len(train_hist))
            test_pct = (test_hist + eps) / (test_hist.sum() + eps * len(test_hist))
            return float(np.sum((test_pct - train_pct) * np.log(test_pct / train_pct)))
            
        for f in features:
            if f in df.columns:
                psi = _compute_psi(train_df[f], holdout_df[f])
                print(f"Calculated PSI for {f}: {psi:.4f}")

if __name__ == '__main__':
    run_analysis()
