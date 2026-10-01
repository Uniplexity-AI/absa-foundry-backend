"""
Train Churn Model based on ABSA Feature Store (`feature_store_churn`).
"""
import os
import pickle
import logging
import numpy as np
import xgboost as xgb
from sklearn.metrics import roc_auc_score, average_precision_score, precision_score, recall_score
import sys

# Ensure data_loader can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from banking_ml_python.data_loader import load_training_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def walk_forward_split(df):
    dates = sorted(df['snapshot_month'].unique())
    for i in range(1, len(dates)):
        train_dates = dates[:i]
        test_date = dates[i]
        
        train_idx = df.index[df['snapshot_month'].isin(train_dates)]
        test_idx = df.index[df['snapshot_month'] == test_date]
        
        yield train_idx, test_idx, test_date

def main():
    os.makedirs('models', exist_ok=True)
    
    # Load data from feature_store_shared JOIN feature_store_churn
    df = load_training_data(model_type='churn', target_columns=['churn_30d', 'churn_90d'])
    if df.empty:
        logger.error("No training data found for churn.")
        sys.exit(1)

    # Exclude metadata and labels
    exclude_cols = ['customer_id', 'snapshot_month', 'churn_30d', 'churn_90d']
    feature_cols = [c for c in df.columns if c not in exclude_cols and pd.api.types.is_numeric_dtype(df[c])]

    logger.info(f"Using {len(feature_cols)} numeric features.")
    
    X = df[feature_cols]
    y = df['churn_90d']  # Primary target for churn
    
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        eval_metric='logloss',
        use_label_encoder=False,
        random_state=42,
        scale_pos_weight=max(1, (len(y) - y.sum()) / max(1, y.sum()))
    )
    
    # Walk-forward validation
    for train_idx, test_idx, test_date in walk_forward_split(df):
        X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
        X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]
        
        if len(np.unique(y_test)) < 2:
            logger.warning(f"Skipping fold {test_date} - only one class in test set.")
            continue
            
        model.fit(X_train, y_train)
        y_prob = model.predict_proba(X_test)[:, 1]
        
        roc_auc = roc_auc_score(y_test, y_prob)
        pr_auc = average_precision_score(y_test, y_prob)
        
        threshold_10pct = np.percentile(y_prob, 90)
        y_pred_top10 = (y_prob >= threshold_10pct).astype(int)
        recall_top10 = recall_score(y_test, y_pred_top10, zero_division=0)
        
        logger.info(f"Fold {test_date}: ROC-AUC={roc_auc:.3f}, PR-AUC={pr_auc:.3f}, Recall@10%={recall_top10:.3f}")
        
    logger.info("Training final churn model on all data.")
    model.fit(X, y)
    
    model_path = "models/churn_model_v2.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({'model': model, 'features': feature_cols}, f)
    logger.info(f"Saved churn model to {model_path}")

if __name__ == "__main__":
    import pandas as pd
    main()
