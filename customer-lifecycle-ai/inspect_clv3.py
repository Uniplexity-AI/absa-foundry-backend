import joblib, numpy as np, psycopg2

# Load model
model = joblib.load("models/customer-lifetime-value-prediction/lightgbm_clv_model.pkl")

# Load actual feature rows for test customers
conn = psycopg2.connect("postgresql://postgres:wamulehi@localhost:5432/etl_clean")
cur = conn.cursor()
cur.execute("SELECT total_amount_90d, total_amount_180d, avg_amount_90d, txn_count_90d, txn_count_365d FROM customer_features WHERE as_of_date = '2026-07-17' ORDER BY total_amount_90d DESC LIMIT 5")
rows = cur.fetchall()
print("Top 5 customers by 90d volume:")
for r in rows:
    print("  90d_vol={}, 180d_vol={}, avg_amt={}, cnt_90d={}, cnt_365d={}".format(*r))
conn.close()

# Run a test prediction with one real row to see the scale
from app.models.clv_predictor import CLVPredictor
predictor = CLVPredictor()
print("\nCLV model loaded:", predictor.is_model_loaded)

# Load from feature service
import requests
resp = requests.get("http://localhost:8002/features/CUST0000886/latest")
feat = resp.json()
print("CUST0000886 features - total_amount_90d:", feat.get("total_amount_90d"))
clvs = predictor.predict_batch([feat])
print("Predicted CLV for CUST0000886:", clvs)
