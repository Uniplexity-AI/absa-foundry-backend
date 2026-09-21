
import sys
sys.path.append(".")
from shared.auth.user_repository import UserRepository
repo = UserRepository()
conn = repo._pool.getconn()
cur = conn.cursor()
cur.execute("INSERT INTO iam.users (username, email, dn, password_hash, display_name) VALUES (%s, %s, %s, %s, %s) RETURNING user_id", ("test99", "test99@ab.com", "test99dn", "hash", "test99"))
user_id = cur.fetchone()[0]
conn.commit()
repo._pool.putconn(conn)
print("Created:", user_id)
print("Deleting:", user_id)
try:
    res = repo.delete_user(str(user_id))
    print("Result:", res)
except Exception as e:
    import traceback
    traceback.print_exc()

