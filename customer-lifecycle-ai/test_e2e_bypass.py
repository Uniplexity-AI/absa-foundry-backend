
import sys
sys.path.append(".")
from shared.auth.user_repository import UserRepository
repo = UserRepository()
conn = repo._pool.getconn()
cur = conn.cursor()
cur.execute("SELECT user_id FROM iam.users LIMIT 1")
uid = cur.fetchone()[0]
repo._pool.putconn(conn)
print("UID", uid)

