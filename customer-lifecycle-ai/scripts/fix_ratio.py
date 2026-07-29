"""Fix credit_to_debit_ratio_90d — needs second pass after sums are populated."""
import sys,os;sys.path.insert(0,'.')
from shared.config.settings import settings
import psycopg2
conn=psycopg2.connect(settings.database_target_url_sync,connect_timeout=10)
cur=conn.cursor()

for dt in ['2026-07-17','2026-07-22','2026-07-27']:
    cur.execute("""
    UPDATE customer_features SET
        credit_to_debit_ratio_90d = CASE
            WHEN debit_sum_30d IS NULL OR debit_sum_30d = 0 THEN NULL
            ELSE ROUND(credit_sum_30d::numeric / debit_sum_30d, 2)
        END
    WHERE as_of_date = %s::date
    """, (dt,))
    print(f"{dt}: {cur.rowcount} rows checked")
    conn.commit()

# Verify
cur.execute("""
SELECT COUNT(*) FILTER (WHERE credit_to_debit_ratio_90d IS NOT NULL),
       ROUND(AVG(credit_to_debit_ratio_90d)::numeric,2)
FROM customer_features WHERE as_of_date='2026-07-27'
""")
nn, avg = cur.fetchone()
print(f"\ncredit_to_debit_ratio_90d: {nn} non-null, avg={avg}")

conn.close()
