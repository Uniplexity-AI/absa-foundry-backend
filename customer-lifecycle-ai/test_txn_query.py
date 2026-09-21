import psycopg2
conn = psycopg2.connect('postgresql://postgres:wamulehi@localhost:5432/etl_validation')
cur = conn.cursor()

# Check transactions_core tables
cur.execute("SELECT COUNT(*), MIN(transaction_date), MAX(transaction_date) FROM transactions_core_batch1")
print("batch1:", cur.fetchone())
cur.execute("SELECT COUNT(*), MIN(transaction_date), MAX(transaction_date) FROM transactions_core_batch2")
print("batch2:", cur.fetchone())

# Sample row
cur.execute("SELECT * FROM transactions_core_batch1 LIMIT 1")
cols = [d[0] for d in cur.description]
print("\nColumns:", cols)
print("Sample:", cur.fetchone())

# What's the DB the feature engineering service uses?
