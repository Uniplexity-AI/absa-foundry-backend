"""Verify engagement scores after regeneration."""
import sys,os;sys.path.insert(0,'.')
from shared.config.settings import settings
import psycopg2
conn=psycopg2.connect(settings.database_target_url_sync,connect_timeout=10)
cur=conn.cursor()

cur.execute("""
SELECT CASE WHEN engagement_score IS NULL THEN 'NULL'
     WHEN engagement_score = 0 THEN 'Zero'
     WHEN engagement_score < 20 THEN '1-19'
     WHEN engagement_score < 40 THEN '20-39'
     WHEN engagement_score < 60 THEN '40-59'
     ELSE '60+' END AS b, COUNT(*) AS n
FROM customer_features WHERE as_of_date='2026-07-27'
GROUP BY 1 ORDER BY 1
""")
print("engagement_score after fix (2026-07-27):")
for r in cur.fetchall(): print(f"  {r[0]:>8s}: {r[1]}")

cur.execute("SELECT AVG(behav_frequency_score) FROM customer_features WHERE as_of_date='2026-07-27' AND txn_count_90d>0")
print(f"\nAvg frequency_score (active customers): {cur.fetchone()[0]:.1f}")

cur.execute("SELECT AVG(engagement_score) FROM customer_features WHERE as_of_date='2026-07-27' AND txn_count_90d>0")
print(f"Avg engagement_score (active customers): {cur.fetchone()[0]:.1f}")

conn.close()
