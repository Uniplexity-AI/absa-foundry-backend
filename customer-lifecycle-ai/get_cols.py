import psycopg2
conn = psycopg2.connect('dbname=etl_clean user=postgres password=wamulehi host=localhost')
cur = conn.cursor()
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'customers_clean';")
for r in cur.fetchall():
    print(f"{r[0]}: {r[1]}")
