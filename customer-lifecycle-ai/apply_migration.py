sql = '''
ALTER TABLE public.customers_clean ADD COLUMN IF NOT EXISTS next_of_kin_name VARCHAR(128);
ALTER TABLE public.customers_clean ADD COLUMN IF NOT EXISTS next_of_kin_relationship VARCHAR(64);
ALTER TABLE public.customers_clean ADD COLUMN IF NOT EXISTS next_of_kin_phone VARCHAR(32);
'''
open('database/migrations/019_customer_next_of_kin.sql', 'w').write(sql)
import psycopg2
conn = psycopg2.connect('postgresql://postgres:wamulehi@localhost:5432/etl_clean')
conn.autocommit = True
cur = conn.cursor()
cur.execute(sql)
print('Migration applied!')
