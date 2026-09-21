import psycopg2

conn = psycopg2.connect("postgresql://postgres:wamulehi@localhost:5432/etl_clean")
cur = conn.cursor()

# Check what tables we have for transactions
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

# Check if customer_transactions_clean exists and has data
if 'customer_transactions_clean' in tables:
    cur.execute("SELECT COUNT(*), MIN(transaction_date), MAX(transaction_date) FROM customer_transactions_clean")
    print("Txn table:", cur.fetchone())
    
# What about the raw txns table?
for t in tables:
    if 'txn' in t or 'transaction' in t:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cur.fetchone()[0]
        print(f"{t}: {cnt} rows")
conn.close()
