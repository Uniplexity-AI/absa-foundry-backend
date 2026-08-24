import psycopg2
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score
import xgboost as xgb

def run_leakage_analysis():
    print("Connecting to DB...")
    conn = psycopg2.connect("postgresql://postgres:wamulehi@localhost:5432/etl_clean")
    
    # Load July 17 data
    df = pd.read_sql("SELECT * FROM customer_features WHERE as_of_date = '2026-07-17'", conn)
    
    if df.empty:
        print("No data for 2026-07-17")
        return
        
    print(f"Loaded {len(df)} rows.")
    
    # Create target
    def get_label(status):
        if status == 'Closed': return 1
        if status and status != 'Closed': return 0
        return None
        
    df['target'] = df['rel_customer_status'].apply(get_label)
    df = df.dropna(subset=['target'])
    print(f"Rows after dropping null targets: {len(df)}, Positives: {df['target'].sum()}")
    
    # Identify leakage features manually
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    exclude = ['id', 'target']
    features = [c for c in numeric_cols if c not in exclude]
    
    # Check correlation with target
    corrs = []
    for f in features:
        corr = df[f].corr(df['target'])
        if pd.notnull(corr):
            corrs.append((f, corr))
            
    corrs.sort(key=lambda x: abs(x[1]), reverse=True)
    print("\nTop 10 features correlated with target:")
    for f, c in corrs[:10]:
        print(f"  {f}: {c:.4f}")

if __name__ == '__main__':
    run_leakage_analysis()
