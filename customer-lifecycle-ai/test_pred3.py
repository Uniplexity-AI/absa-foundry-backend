import psycopg2
import pandas as pd
import joblib
import numpy as np

DB_URL = 'postgresql://postgres:wamulehi@localhost:5432/etl_clean'
conn = psycopg2.connect(DB_URL)
df = pd.read_sql("SELECT * FROM customer_features WHERE customer_id='000000222'", conn)

model = joblib.load('models/customer-lifetime-value-prediction/lightgbm_clv_model.pkl')
features = model.feature_name_
X_df = df[features]

cat_features = getattr(model.booster_, 'pandas_categorical', None)
cats_dict = {cat[0]: list(cat[1]) for cat in cat_features} if cat_features else {}

frame = pd.DataFrame([X_df.iloc[0].to_dict()], columns=features)
for name, categories in cats_dict.items():
    frame[name] = [categories.index(v) if v in categories else -1 for v in frame[name]]

matrix = frame.apply(pd.to_numeric, errors='coerce').astype('float64').to_numpy()
print('Numpy prediction:', model.predict(matrix))

X_df_cats = df[features].copy()
if cat_features:
    for cat in cat_features:
        if cat[0] in X_df_cats.columns:
            X_df_cats[cat[0]] = pd.Categorical(X_df_cats[cat[0]].astype(str), categories=cat[1])
for c in X_df_cats.columns:
    if X_df_cats[c].dtype != 'category':
        X_df_cats[c] = pd.to_numeric(X_df_cats[c], errors='coerce')

print('DataFrame prediction:', model.predict(X_df_cats))
