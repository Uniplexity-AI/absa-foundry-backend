
import sys
sys.path.append(".")
from shared.auth.user_repository import UserRepository
repo = UserRepository()
user = repo.get_by_username("rm.demo")
if user:
    print("Deleting rm.demo", user["user_id"])
    try:
        res = repo.delete_user(user["user_id"])
        print("Result:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()
else:
    print("rm.demo not found")

