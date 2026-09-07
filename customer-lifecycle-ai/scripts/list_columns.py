"""List actual column names in customer_features."""
import psycopg2
from shared.config.settings import settings

url = settings.database_target_url.replace("postgresql+asyncpg://", "postgresql://")
conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='customer_features' ORDER BY ordinal_position")
for r in cur.fetchall():
    print(r[0])
cur.close()
conn.close()
