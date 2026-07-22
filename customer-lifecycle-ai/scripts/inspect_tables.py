"""Inspect all tables in etl_validation."""
import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5432, dbname="etl_validation",
    user="postgres", password="wamulehi",
)
cur = conn.cursor()

tables = ["raw_customers", "raw_transactions", "raw_interactions", "customer_transactions"]

for tbl in tables:
    cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = %s ORDER BY ordinal_position",
        (tbl,),
    )
    cols = cur.fetchall()
    if cols:
        print(f"\n{tbl} ({len(cols)} cols):")
        for col in cols:
            print(f"  {col[0]:30s} {col[1]}")

conn.close()
