"""Verify health score backfill in customer_states."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config.settings import settings
import psycopg2

conn = psycopg2.connect(settings.database_target_url_sync, connect_timeout=10)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM customer_states WHERE as_of_date = %s", ("2026-07-27",))
total = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM customer_states WHERE as_of_date = %s AND health_score IS NOT NULL", ("2026-07-27",))
filled = cur.fetchone()[0]

print(f"States on 2026-07-27: {total} total, {filled} with health_score ({100*filled//total if total else 0}%)")

cur.execute("SELECT health_score FROM customer_states WHERE customer_id = %s AND as_of_date = %s", ("CUST00001", "2026-07-27"))
row = cur.fetchone()
print(f"CUST00001 health_score: {row[0] if row else 'NOT FOUND'}")

# Show distribution
cur.execute("""
    SELECT
        CASE
            WHEN health_score >= 70 THEN 'Healthy (70-100)'
            WHEN health_score >= 40 THEN 'At Risk (40-69)'
            WHEN health_score IS NOT NULL THEN 'Critical (0-39)'
            ELSE 'Not scored'
        END AS category,
        COUNT(*) AS count
    FROM customer_states
    WHERE as_of_date = '2026-07-27'
    GROUP BY category
    ORDER BY category
""")
print("\nHealth score distribution:")
for cat, cnt in cur.fetchall():
    print(f"  {cat}: {cnt}")

conn.close()
print("\nVerification complete!")
