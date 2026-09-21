
import sys
import asyncio
sys.path.append(".")
from shared.auth.user_repository import UserRepository
from shared.config.settings import settings
repo = UserRepository()
print(repo.get_roles())

