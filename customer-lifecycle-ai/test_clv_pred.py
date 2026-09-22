import psycopg2
import pandas as pd
import sys
import os
sys.path.append('services/prediction-service')
from app.models.clv_predictor import CLVPredictor

DB_URL = 'postgresql://postgres:wamulehi@localhost:5432/etl_clean'
conn = psycopg2.connect(DB_URL)
df = pd.read_sql("SELECT * FROM customer_features WHERE customer_id='000000222'", conn)

predictor = CLVPredictor(os.path.abspath('models/customer-lifetime-value-prediction/lightgbm_clv_model.pkl'))
rows = [df.iloc[0].to_dict()]
print("Prediction:", predictor.predict_batch(rows))
