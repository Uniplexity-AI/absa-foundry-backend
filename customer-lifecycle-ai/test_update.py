
import sys
sys.path.append(".")
from shared.auth.user_repository import UserRepository
repo = UserRepository()
conn = repo._pool.getconn()
cur = conn.cursor()
try:
    cur.execute("UPDATE iam.service_accounts SET created_by = NULL WHERE created_by = %s", ("123e4567-e89b-12d3-a456-426614174000",))
    print("SERVICE ACCOUNTS OK")
except Exception as e:
    print("ERROR:", e)

