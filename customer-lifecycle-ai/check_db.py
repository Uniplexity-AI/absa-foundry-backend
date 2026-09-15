import psycopg2
conn = psycopg2.connect("postgresql://postgres:wamulehi@localhost:5432/etl_clean")
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=chr(39)||chr(112)||chr(117)||chr(98)||chr(108)||chr(105)||chr(99)||chr(39) ORDER BY 1")
tables = [r[0] for r in cur.fetchall()]
print("TABLES:", tables)
cur.execute("SELECT SUM(CASE WHEN engagement_score IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN behav_txn_count_7d IS NOT NULL THEN 1 ELSE 0 END), COUNT(*) FROM customer_features")
print("Engagement data:", cur.fetchone())
for t in tables:
    cur.execute("SELECT COUNT(*) FROM " + t)
    print(t + ":", cur.fetchone()[0])
conn.close()
