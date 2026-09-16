import psycopg2

# Try source database
conn = psycopg2.connect("postgresql://postgres:wamulehi@localhost:5432/etl_validation")
cur = conn.cursor()

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
tables = [r[0] for r in cur.fetchall()]
print("Source DB tables:", tables)

for t in tables:
    if 'txn' in t or 'transaction' in t:
        cur.execute(f"SELECT COUNT(*), MIN(transaction_date), MAX(transaction_date) FROM {t}")
        print(f"{t}: {cur.fetchone()}")

conn.close()
