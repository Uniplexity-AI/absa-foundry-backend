"""
Target generation and model training for Customer Value Intelligence.
Phase 1: Construct T+90 labels dynamically.
Phase 2: Feature extraction.
Phase 3: Train XGBoost Classifier (Erosion) + Regressor (Future Value).
Phase 4: SHAP Explainability (integrated in predict).
"""
import argparse
import datetime as dt
import json
import logging
import os
import pickle
import sys

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from sklearn.metrics import average_precision_score, mean_absolute_error, mean_squared_error, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
import xgboost as xgb
try:
    import shap
except ImportError:
    shap = None

from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _jsonable(obj):
    """Recursively convert numpy / pandas / date values into JSON-serializable ones."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (dt.datetime, dt.date)):
        return obj.isoformat()
    return obj

def get_db_connection():
    load_dotenv()
    db_url = os.environ.get("DATABASE_TARGET_URL_SYNC") or "postgresql://postgres:wamulehi@localhost:5432/etl_clean"
    return psycopg2.connect(db_url)

def extract_features_and_targets(conn) -> pd.DataFrame:
    """Extract features and dynamically compute T+90 targets."""
    
    # We define relationship value as the total incoming credits in the last 90 days.
    # To compute T+90 relationship value, we sum credits between T and T+90.
    
    query = """
    WITH base_features AS (
        SELECT 
            cf.customer_id,
            cf.as_of_date,
            cf.total_amount_90d, 
            cf.txn_count_90d,
            cf.days_since_last_txn,
            cf.avg_days_between_txn,
            cf.distinct_channels_90d,
            cf.engagement_score
        FROM customer_features cf
        WHERE cf.total_amount_90d IS NOT NULL
          AND cf.total_amount_90d > 0 -- Need positive balance to calculate drop percentage
    ),
    future_value AS (
        SELECT 
            b.customer_id,
            b.as_of_date,
            COALESCE(SUM(t.amount), 0) AS future_total_amount_90d
        FROM base_features b
        LEFT JOIN customer_transactions_clean t 
            ON t.customer_id = b.customer_id
            AND t.transaction_type = 'CREDIT'
            AND t.transaction_date > b.as_of_date
            AND t.transaction_date <= b.as_of_date + INTERVAL '90 days'
        GROUP BY b.customer_id, b.as_of_date
    )
    SELECT 
        b.*,
        f.future_total_amount_90d,
        CASE 
            WHEN (f.future_total_amount_90d - b.total_amount_90d) / b.total_amount_90d < -0.25 THEN 1
            ELSE 0
        END AS is_value_eroding
    FROM base_features b
    JOIN future_value f ON b.customer_id = f.customer_id AND b.as_of_date = f.as_of_date
    ORDER BY b.as_of_date, b.customer_id;
    """
    
    logger.info("Extracting features and generating T+90 targets from database...")
    df = pd.read_sql(query, conn)
    logger.info(f"Extracted {len(df)} rows.")
    return df

def walk_forward_split(df: pd.DataFrame):
    """Yield train and test indices for walk-forward validation based on dates."""
    dates = sorted(df['as_of_date'].unique())
    
    # Example walk-forward:
    # Train on dates up to D_i, validate on D_{i+1}
    for i in range(1, len(dates)):
        train_dates = dates[:i]
        test_date = dates[i]
        
        train_idx = df.index[df['as_of_date'].isin(train_dates)]
        test_idx = df.index[df['as_of_date'] == test_date]
        
        yield train_idx, test_idx, test_date

def train_erosion_model(df: pd.DataFrame, feature_cols: list) -> tuple[xgb.XGBClassifier, list[dict]]:
    """Train XGBoost Classifier for Value Erosion Risk with Walk-Forward Validation.

    Returns the final model plus the per-fold walk-forward metrics (persisted to
    models/value_models_metrics.json for registry registration).
    """
    logger.info("Training Value Erosion Model (Classification)...")
    
    X = df[feature_cols]
    y = df['is_value_eroding']
    
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
    metrics = []
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
        
        # Recall @ Top 10%
        threshold_10pct = np.percentile(y_prob, 90)
        y_pred_top10 = (y_prob >= threshold_10pct).astype(int)
        recall_top10 = recall_score(y_test, y_pred_top10, zero_division=0)
        precision_top10 = precision_score(y_test, y_pred_top10, zero_division=0)
        
        metrics.append({
            'date': test_date,
            'roc_auc': roc_auc,
            'pr_auc': pr_auc,
            'recall_top10': recall_top10,
            'precision_top10': precision_top10
        })
        
        logger.info(f"Fold {test_date}: ROC-AUC={roc_auc:.3f}, PR-AUC={pr_auc:.3f}, Recall@10%={recall_top10:.3f}, Precision@10%={precision_top10:.3f}")
        
    # Final train on all data
    logger.info("Training final erosion model on all data.")
    model.fit(X, y)
    return model, metrics

def train_forecast_model(df: pd.DataFrame, feature_cols: list) -> tuple[xgb.XGBRegressor, list[dict]]:
    """Train XGBoost Regressor for Future Value Forecast.

    Returns the final model plus the per-fold walk-forward metrics.
    """
    logger.info("Training Future Value Forecast Model (Regression)...")
    
    X = df[feature_cols]
    # Log transform the target to handle long-tail distributions
    y = np.log1p(df['future_total_amount_90d'])
    
    model = xgb.XGBRegressor(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        eval_metric='rmse',
        random_state=42
    )
    
    # Walk-forward validation
    forecast_metrics = []
    for train_idx, test_idx, test_date in walk_forward_split(df):
        X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
        X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]
        
        model.fit(X_train, y_train)
        y_pred_log = model.predict(X_test)
        
        # Convert back to actual amounts
        y_pred = np.expm1(y_pred_log)
        y_true = np.expm1(y_test)
        
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        mae = mean_absolute_error(y_true, y_pred)
        
        forecast_metrics.append({
            'date': test_date,
            'rmse': rmse,
            'mae': mae,
        })
        
        logger.info(f"Fold {test_date}: RMSE={rmse:.2f}, MAE={mae:.2f}")
        
    # Final train on all data
    logger.info("Training final forecast model on all data.")
    model.fit(X, y)
    return model, forecast_metrics

def generate_shap_explanations(model, X, is_classification=True):
    """Generate SHAP values for the dataset to verify explainability works."""
    if shap is None:
        logger.warning("SHAP is not installed. Skipping explanations.")
        return None, None
    logger.info("Generating SHAP explanations...")
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)
    return explainer, shap_values

def main():
    os.makedirs('models', exist_ok=True)
    
    try:
        conn = get_db_connection()
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)
        
    df = extract_features_and_targets(conn)
    conn.close()
    
    if df.empty:
        logger.error("No data extracted. Ensure database is populated.")
        sys.exit(1)
        
    feature_cols = [c for c in df.columns if c not in [
        'customer_id', 'as_of_date', 'future_total_amount_90d', 'is_value_eroding'
    ]]
    
    # 1. Train Classification Model (Erosion Risk)
    erosion_model, erosion_folds = train_erosion_model(df, feature_cols)
    erosion_model_path = "models/value_erosion_v1.pkl"
    with open(erosion_model_path, "wb") as f:
        pickle.dump({'model': erosion_model, 'features': feature_cols}, f)
    logger.info(f"Saved erosion model to {erosion_model_path}")
    
    # 2. Train Regression Model (Future Value)
    forecast_model, forecast_folds = train_forecast_model(df, feature_cols)
    forecast_model_path = "models/value_forecast_v1.pkl"
    with open(forecast_model_path, "wb") as f:
        pickle.dump({'model': forecast_model, 'features': feature_cols}, f)
    logger.info(f"Saved forecast model to {forecast_model_path}")

    # 2b. Persist metrics + lineage so scripts/register_value_models.py can
    #     register these models without re-evaluating them.
    dates = sorted({d.isoformat() if hasattr(d, 'isoformat') else str(d) for d in df['as_of_date'].unique()})
    metadata = {
        'trained_at': dt.date.today().isoformat(),
        'training_rows': int(len(df)),
        'as_of_dates': dates,
        'features': list(feature_cols),
        'feature_count': len(feature_cols),
        'targets': {
            'erosion': 'is_value_eroding = 1 when (future_total_amount_90d - total_amount_90d) / total_amount_90d < -0.25',
            'forecast': 'future_total_amount_90d = SUM(CREDIT amount) in (as_of_date, as_of_date + 90 days]',
        },
        'hyperparameters': {
            'erosion': {'n_estimators': 100, 'max_depth': 4, 'learning_rate': 0.1,
                        'eval_metric': 'logloss', 'random_state': 42},
            'forecast': {'n_estimators': 100, 'max_depth': 4, 'learning_rate': 0.1,
                         'eval_metric': 'rmse', 'random_state': 42},
        },
        'validation': {
            'strategy': 'walk_forward',
            'erosion_folds': erosion_folds,
            'forecast_folds': forecast_folds,
        },
        'shap_available': shap is not None,
    }
    metrics_path = "models/value_models_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(_jsonable(metadata), f, indent=2)
        f.write("\n")
    logger.info(f"Saved value-model metrics to {metrics_path}")
    
    # 3. Test SHAP
    logger.info("Testing SHAP integration on a subset...")
    X_sample = df[feature_cols].head(100)
    generate_shap_explanations(erosion_model, X_sample)
    
    logger.info("Pipeline completed successfully.")

if __name__ == "__main__":
    main()
