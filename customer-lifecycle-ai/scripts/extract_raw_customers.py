"""
Extract text/data from raw_customers table in the source database.
Reads credentials from .env file via python-dotenv.
"""
import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Connect to source DB using env vars with fallbacks
conn = psycopg2.connect(
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    dbname=os.getenv("POSTGRES_DB", "customer_lifecycle"),
    user=os.getenv("POSTGRES_USER", "clp_user"),
    password=os.getenv("POSTGRES_PASSWORD", "clp_password"),
)

cur = conn.cursor()

# First, list all tables to find raw_customers
cur.execute(
    "SELECT table_schema, table_name FROM information_schema.tables "
    "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
    "ORDER BY table_schema, table_name"
)
tables = cur.fetchall()
print("=== Available Tables ===")
for schema, table in tables:
    print(f"  {schema}.{table}")

# Now query raw_customers
print("\n=== raw_customers: Schema ===")
cur.execute(
    "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
    "WHERE table_name = 'raw_customers' ORDER BY ordinal_position"
)
columns = cur.fetchall()
for col in columns:
    print(f"  {col[0]:25s} {col[1]:15s} nullable={col[2]}")

print("\n=== raw_customers: Row Count ===")
cur.execute("SELECT COUNT(*) FROM raw_customers")
count = cur.fetchone()[0]
print(f"  Total rows: {count}")

print("\n=== raw_customers: First 20 Rows ===")
cur.execute("SELECT * FROM raw_customers LIMIT 20")
rows = cur.fetchall()
col_names = [desc[0] for desc in cur.description]
df = pd.DataFrame(rows, columns=col_names)
print(df.to_string(index=False))

print("\n=== raw_customers: Summary Stats ===")
print(df.describe(include="all").to_string())

conn.close()
