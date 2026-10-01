"""
Train CLV Model based on ABSA Feature Store (`feature_store_clv`).
"""
import os
import pickle
import logging
import numpy as np
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error
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
    os.makedirs('models/customer-lifetime-value-prediction', exist_ok=True)
    
    # Load data from feature_store_shared JOIN feature_store_clv
    df = load_training_data(model_type='clv', target_columns=['target_clv_12m'])
    if df.empty:
        logger.error("No training data found for CLV.")
        sys.exit(1)

    exclude_cols = ['customer_id', 'snapshot_month', 'target_fee_income_12m', 'target_margin_12m', 'target_clv_12m']
    feature_cols = [c for c in df.columns if c not in exclude_cols and pd.api.types.is_numeric_dtype(df[c])]

    logger.info(f"Using {len(feature_cols)} numeric features.")
    
    X = df[feature_cols]
    y = df['target_clv_12m'].fillna(0).clip(lower=0)
    
    import lightgbm as lgb
    
    model = lgb.LGBMRegressor(
        objective="tweedie", 
        tweedie_variance_power=1.5,
        n_estimators=500, 
        learning_rate=0.05, 
        num_leaves=31,
        subsample=0.8, 
        colsample_bytree=0.8, 
        min_child_samples=10,
        random_state=42, 
        n_jobs=-1, 
        force_col_wise=True
    )
    
    for train_idx, test_idx, test_date in walk_forward_split(df):
        X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
        X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]
        
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        mae = mean_absolute_error(y_test, y_pred)
        
        logger.info(f"Fold {test_date}: RMSE={rmse:.2f}, MAE={mae:.2f}")
        
    logger.info("Training final CLV model on all data.")
    model.fit(X, y)
    
    model_path = "models/customer-lifetime-value-prediction/clv_model_v2.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({'model': model, 'features': feature_cols}, f)
    logger.info(f"Saved CLV model to {model_path}")

if __name__ == "__main__":
    import pandas as pd
    main()
