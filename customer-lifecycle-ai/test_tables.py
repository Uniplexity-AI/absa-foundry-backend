
import sys
import psycopg2
sys.path.append(".")
from shared.config.settings import settings
conn = psycopg2.connect(settings.database_url_sync)
cur = conn.cursor()
cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = %s", ("iam",))
print(cur.fetchall())

