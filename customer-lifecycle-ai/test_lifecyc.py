import psycopg2
import pandas as pd
import sys
import os
sys.path.append('services/prediction-service')
from app.models.lifecycle_predictor import LifecyclePredictor

DB_URL = 'postgresql://postgres:wamulehi@localhost:5432/etl_clean'
conn = psycopg2.connect(DB_URL)
df = pd.read_sql("SELECT * FROM customer_features LIMIT 1", conn)

predictor = LifecyclePredictor()
rows = [df.iloc[0].to_dict()]
print("Prediction:", predictor.predict_batch(rows, 90))
