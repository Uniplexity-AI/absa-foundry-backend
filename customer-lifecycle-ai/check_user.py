
import sys
import psycopg2
sys.path.append(".")
from shared.config.settings import settings
conn = psycopg2.connect(settings.database_url_sync)
cur = conn.cursor()
cur.execute("SELECT u.username, u.email, r.role_name FROM iam.users u JOIN iam.user_roles ur ON u.user_id = ur.user_id JOIN iam.roles r ON ur.role_id = r.role_id")
print(cur.fetchall())

