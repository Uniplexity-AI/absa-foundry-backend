import psycopg2
import pandas as pd
import sys, os
sys.path.append('services/prediction-service')
from app.models.clv_predictor import CLVPredictor

DB_URL = 'postgresql://postgres:wamulehi@localhost:5432/etl_clean'
conn = psycopg2.connect(DB_URL)
df = pd.read_sql("SELECT * FROM customer_features LIMIT 5", conn)

predictor = CLVPredictor(os.path.abspath('models/customer-lifetime-value-prediction/lightgbm_clv_model.pkl'))
rows = df.to_dict(orient='records')
results = predictor.predict_batch(rows)
for r, v in zip(rows, results):
    print(f"customer_id={r['customer_id']}  total_amount_90d={r.get('total_amount_90d', '?')}  CLV_pred={v:.2f}")
