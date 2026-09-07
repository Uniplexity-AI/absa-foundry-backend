"""Add Phase 2 columns to customer_features."""
import psycopg2
c = psycopg2.connect(host="localhost", port=5432, dbname="etl_clean", user="postgres", password="wamulehi")
cur = c.cursor()
for col, dtype in [
    ("txn_count_365d", "INT"),
    ("credit_sum_30d", "NUMERIC"),
    ("debit_sum_30d", "NUMERIC"),
    ("credit_to_debit_ratio_90d", "FLOAT"),
    ("balance_trend_90d", "TEXT"),
    ("has_salary_credit", "BOOLEAN"),
    ("monthly_income_estimate", "NUMERIC"),
]:
    cur.execute(f"ALTER TABLE customer_features ADD COLUMN IF NOT EXISTS {col} {dtype}")
c.commit()
c.close()
print("7 new columns added to customer_features")
