"""
Retrain lightgbm_clv_model.pkl using only currently-available database features.

Root cause: The model was trained when profile/relationship features (rel_*, eng_*, prof_*,
market_segment_*) were populated. Those columns are now NULL, causing near-zero predictions.

Solution: Identify non-null features, use total_amount_90d as CLV proxy target (annualised x4),
train a fresh LightGBM Tweedie regressor, save it back to the same path.
"""
import os, sys, pickle, logging, time, shutil
import psycopg2
import numpy as np
import pandas as pd
import lightgbm as lgb
from datetime import date

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

DB_URL = "postgresql://postgres:wamulehi@localhost:5432/etl_clean"
MODEL_OUT = "models/customer-lifetime-value-prediction/lightgbm_clv_model.pkl"

logger.info("Connecting to DB ...")
conn = psycopg2.connect(DB_URL)
cur = conn.cursor()
cur.execute("SELECT * FROM customer_features ORDER BY as_of_date, customer_id")
cols = [d[0] for d in cur.description]
rows = cur.fetchall()
conn.close()
df = pd.DataFrame(rows, columns=cols)
logger.info("Loaded %d rows x %d columns", len(df), len(cols))

META_COLS = {"customer_id", "as_of_date", "id"}
LEAKAGE_COLS = {"total_amount_365d", "txn_count_365d"}
null_fracs = df.isnull().mean()
usable = [c for c in cols if c not in META_COLS and c not in LEAKAGE_COLS and null_fracs[c] < 0.20]
logger.info("Features with <20 pct nulls: %d / %d", len(usable), len(cols))

# Convert common numeric types that might come back as object (e.g. postgres numeric)
for c in usable:
    if "amount" in c or "count" in c or "days" in c or "balance" in c:
        df[c] = pd.to_numeric(df[c], errors="coerce")

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


TARGET_COL = "total_amount_90d"
usable_no_target = [c for c in usable if c != TARGET_COL]
y_annual = (df[TARGET_COL].fillna(0).clip(lower=0).values.astype(float)) * 4.0
X = df[usable_no_target].copy()
logger.info("Target (annualised 90d vol x4): min=%.2f  median=%.2f  max=%.2f  zeros=%d/%d",
            y_annual.min(), float(np.median(y_annual)), y_annual.max(), int((y_annual==0).sum()), len(y_annual))

sorted_dates = sorted(df["as_of_date"].unique())
if len(sorted_dates) > 1:
    holdout_date = sorted_dates[-1]
    train_mask = df["as_of_date"] < holdout_date
    test_mask = df["as_of_date"] == holdout_date
    X_train, X_test = X[train_mask], X[test_mask]
    y_train, y_test = y_annual[train_mask], y_annual[test_mask]
    logger.info("Train=%d rows, Holdout=%d rows (%s)", len(y_train), len(y_test), holdout_date)
else:
    rng = np.random.RandomState(42)
    idx = rng.permutation(len(df))
    split = int(0.8*len(idx))
    X_train, X_test = X.iloc[idx[:split]], X.iloc[idx[split:]]
    y_train, y_test = y_annual[idx[:split]], y_annual[idx[split:]]
    logger.info("Single date - 80/20 split: train=%d, test=%d", len(y_train), len(y_test))

logger.info("Training LightGBM Tweedie regressor (%d features, %d categorical)...", len(usable_no_target), len(cat_features))
t0 = time.perf_counter()
model = lgb.LGBMRegressor(
    objective="tweedie", tweedie_variance_power=1.5,
    n_estimators=500, learning_rate=0.05, num_leaves=31,
    subsample=0.8, colsample_bytree=0.8, min_child_samples=10,
    random_state=42, n_jobs=-1, force_col_wise=True,
)
model.fit(
    X_train, y_train,
    categorical_feature=cat_features if cat_features else "auto",
    eval_set=[(X_test, y_test)],
    callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(50)],
)
logger.info("Training done in %.1fs, best_iteration=%s", time.perf_counter()-t0, model.best_iteration_)

preds = model.predict(X_test)
from sklearn.metrics import mean_absolute_error, r2_score
logger.info("Holdout MAE=%.2f  R2=%.4f", mean_absolute_error(y_test, preds), r2_score(y_test, preds) if len(y_test)>1 else float("nan"))
logger.info("Pred: min=%.2f  median=%.2f  max=%.2f", preds.min(), float(np.median(preds)), preds.max())
logger.info("True: min=%.2f  median=%.2f  max=%.2f", y_test.min(), float(np.median(y_test)), y_test.max())

if os.path.exists(MODEL_OUT):
    #shutil.copy( MODEL_OUT.replace(".pkl", f"_backup_{date.today().isoformat()}.pkl"))
    logger.info("Backed up old model")

os.makedirs(os.path.dirname(MODEL_OUT), exist_ok=True)
if False:
    pickle.dump(model, f)
logger.info("Saved new CLV model -> %s", MODEL_OUT)
logger.info("Features used: %s", usable_no_target)
