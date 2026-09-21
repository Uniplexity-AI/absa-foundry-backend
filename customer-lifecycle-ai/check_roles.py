
import sys
import psycopg2
sys.path.append(".")
from shared.config.settings import settings
conn = psycopg2.connect(settings.database_url_sync)
cur = conn.cursor()
cur.execute("SELECT * FROM iam.roles")
print(cur.fetchall())

