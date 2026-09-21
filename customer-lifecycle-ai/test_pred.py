import psycopg2
import pandas as pd
conn = psycopg2.connect('postgresql://postgres:wamulehi@localhost:5432/etl_clean')
df = pd.read_sql("SELECT total_amount_90d FROM customer_features WHERE customer_id='000000222'", conn)
print(df)
