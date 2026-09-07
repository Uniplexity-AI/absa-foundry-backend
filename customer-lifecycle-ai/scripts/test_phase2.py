"""Test Phase 2 SQL directly."""
import sys,os;sys.path.insert(0,'.')
from shared.config.settings import settings
import psycopg2
conn=psycopg2.connect(settings.database_target_url_sync,connect_timeout=10)
cur=conn.cursor()

# Run Phase 2 manually
cur.execute("""
UPDATE customer_features SET
    txn_count_365d = (
        SELECT COUNT(*) FROM customer_transactions_clean t
        WHERE t.customer_id = customer_features.customer_id
          AND t.transaction_date::date > (customer_features.as_of_date - INTERVAL '365 days')
          AND t.transaction_date::date <= customer_features.as_of_date
    )
WHERE as_of_date = '2026-07-27'::date
""")
print(f"txn_count_365d updated: {cur.rowcount} rows")
conn.commit()

# Verify
cur.execute("SELECT COUNT(*) FILTER (WHERE txn_count_365d IS NOT NULL), AVG(txn_count_365d) FROM customer_features WHERE as_of_date='2026-07-27'")
nn, avg = cur.fetchone()
print(f"After manual run: NOT-NULL={nn}, AVG={avg}")

# Now run full Phase 2
from services.feature_engineering_service.app.repository.repository import PHASE2_SQL
cur.execute(PHASE2_SQL, {"as_of_date": "2026-07-27"})
print(f"Full Phase 2: {cur.rowcount} rows")
conn.commit()

# Check all columns
for col in ['txn_count_365d','credit_sum_30d','debit_sum_30d','credit_to_debit_ratio_90d','monthly_income_estimate']:
    cur.execute(f'SELECT COUNT(*) FILTER (WHERE "{col}" IS NOT NULL) FROM customer_features WHERE as_of_date=%s', ('2026-07-27',))
    nn = cur.fetchone()[0]
    print(f"  {col}: NOT-NULL={nn}")

conn.close()
