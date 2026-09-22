import psycopg2
import pandas as pd
import joblib
import numpy as np

DB_URL = 'postgresql://postgres:wamulehi@localhost:5432/etl_clean'
conn = psycopg2.connect(DB_URL)
df = pd.read_sql("SELECT * FROM customer_features WHERE customer_id='000000222'", conn)

model = joblib.load('models/customer-lifetime-value-prediction/lightgbm_clv_model.pkl')
features = model.feature_name_
X_df = df[features].copy()
cat_features = getattr(model.booster_, "pandas_categorical", None)
if cat_features:
    for cat in cat_features:
        if cat[0] in X_df.columns:
            X_df[cat[0]] = pd.Categorical(X_df[cat[0]].astype(str), categories=cat[1])

for c in X_df.columns:
    if X_df[c].dtype != 'category':
        X_df[c] = pd.to_numeric(X_df[c], errors='coerce')

print('DF prediction:', model.predict(X_df))
