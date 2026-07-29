"""Run Phase 2 directly for all dates to fix the NULL columns."""
import sys,os;sys.path.insert(0,'.')
from shared.config.settings import settings
import psycopg2

conn=psycopg2.connect(settings.database_target_url_sync,connect_timeout=10)
cur=conn.cursor()

dates = ['2026-07-17','2026-07-22','2026-07-27']

for dt in dates:
    cur.execute("""
    UPDATE customer_features SET
        txn_count_365d = (
            SELECT COUNT(*) FROM customer_transactions_clean t
            WHERE t.customer_id = customer_features.customer_id
              AND t.transaction_date::date > (customer_features.as_of_date - INTERVAL '365 days')
              AND t.transaction_date::date <= customer_features.as_of_date
        ),
        credit_sum_30d = (
            SELECT COALESCE(SUM(amount), 0)
            FROM customer_transactions_clean t
            WHERE t.customer_id = customer_features.customer_id
              AND t.transaction_date::date > (customer_features.as_of_date - INTERVAL '90 days')
              AND t.transaction_date::date <= customer_features.as_of_date
              AND t.transaction_type = 'CREDIT'
        ),
        debit_sum_30d = (
            SELECT COALESCE(SUM(amount), 0)
            FROM customer_transactions_clean t
            WHERE t.customer_id = customer_features.customer_id
              AND t.transaction_date::date > (customer_features.as_of_date - INTERVAL '90 days')
              AND t.transaction_date::date <= customer_features.as_of_date
              AND t.transaction_type = 'DEBIT'
        ),
        credit_to_debit_ratio_90d = CASE
            WHEN debit_sum_30d = 0 THEN NULL
            ELSE ROUND(credit_sum_30d::numeric / NULLIF(debit_sum_30d, 0), 2)
        END,
        monthly_income_estimate = (
            SELECT ROUND(COALESCE(SUM(amount), 0) / 3.0, 2)
            FROM customer_transactions_clean t2
            WHERE t2.customer_id = customer_features.customer_id
              AND t2.transaction_type = 'CREDIT'
              AND t2.transaction_date::date > (customer_features.as_of_date - INTERVAL '90 days')
              AND t2.transaction_date::date <= customer_features.as_of_date
        ),
        has_salary_credit = (
            SELECT COUNT(DISTINCT DATE_TRUNC('month', transaction_date::date)) >= 3
            FROM customer_transactions_clean t2
            WHERE t2.customer_id = customer_features.customer_id
              AND t2.transaction_type = 'CREDIT'
              AND t2.transaction_date::date > (customer_features.as_of_date - INTERVAL '90 days')
              AND t2.transaction_date::date <= customer_features.as_of_date
        ),
        balance_trend_90d = 'STABLE',
        computed_at = NOW()
    WHERE as_of_date = %s::date
    """, (dt,))
    print(f"{dt}: {cur.rowcount} rows updated")
    conn.commit()

# Verify
print("\nAfter fix (2026-07-27):")
for col, desc in [
    ('txn_count_365d', '365d txn count'),
    ('credit_sum_30d', '90d credit sum (named 30d in DDL)'),
    ('debit_sum_30d', '90d debit sum (named 30d in DDL)'),
    ('credit_to_debit_ratio_90d', 'credit/debit ratio'),
    ('monthly_income_estimate', 'monthly income'),
]:
    cur.execute(f'SELECT COUNT(*) FILTER (WHERE "{col}" IS NOT NULL), ROUND(AVG("{col}")::numeric,1) FROM customer_features WHERE as_of_date=%s', ('2026-07-27',))
    nn, avg = cur.fetchone()
    print(f"  {desc:<40s}: {nn} non-null, avg={avg}")

conn.close()
print("\nDone!")
