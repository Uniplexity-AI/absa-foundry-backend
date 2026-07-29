"""Check if Phase 2 columns are NULL vs zero."""
import sys,os;sys.path.insert(0,'.')
from shared.config.settings import settings
import psycopg2
conn=psycopg2.connect(settings.database_target_url_sync,connect_timeout=10)
cur=conn.cursor()
cols = ['txn_count_365d','credit_sum_30d','debit_sum_30d','credit_to_debit_ratio_90d',
        'monthly_income_estimate','has_salary_credit','balance_trend_90d']
for col in cols:
    cur.execute(f'SELECT COUNT(*) FILTER (WHERE "{col}" IS NULL), COUNT(*) FILTER (WHERE "{col}" IS NOT NULL) FROM customer_features WHERE as_of_date=%s', ('2026-07-27',))
    nulls,nn = cur.fetchone()
    print(f'{col:<35s}: NULL={nulls}, NOT-NULL={nn}')
conn.close()
