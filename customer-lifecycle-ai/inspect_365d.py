import psycopg2

conn = psycopg2.connect("postgresql://postgres:wamulehi@localhost:5432/etl_clean")
cur = conn.cursor()

# Check actual 365d transaction count vs what's stored
cur.execute("""
    SELECT 
        cf.customer_id,
        cf.txn_count_365d AS stored_365d,
        cf.txn_count_90d AS stored_90d,
        cf.txn_count_180d AS stored_180d,
        COUNT(t.transaction_id) FILTER (
            WHERE t.transaction_date::date > ('2026-07-17'::date - INTERVAL '365 days')
        ) AS actual_365d_count
    FROM customer_features cf
    LEFT JOIN customer_transactions_clean t ON t.customer_id = cf.customer_id
        AND t.transaction_date::date <= '2026-07-17'::date
    WHERE cf.as_of_date = '2026-07-17'
    GROUP BY cf.customer_id, cf.txn_count_365d, cf.txn_count_90d, cf.txn_count_180d
    LIMIT 5
""")
rows = cur.fetchall()
print("stored_365d | stored_90d | stored_180d | actual_365d")
for r in rows:
    print(r)

# Check transaction date range
cur.execute("SELECT MIN(transaction_date), MAX(transaction_date) FROM customer_transactions_clean")
print("Tx date range:", cur.fetchone())

conn.close()
