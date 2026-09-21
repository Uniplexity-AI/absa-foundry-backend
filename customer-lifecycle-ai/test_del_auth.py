
import asyncio, httpx, sys
sys.path.append(".")
from shared.auth.user_repository import UserRepository
from shared.auth.authenticator import _create_token
from datetime import timedelta

async def test():
    repo = UserRepository()
    user = repo.get_by_username("admin")
    if not user: return
    token = _create_token({"sub": str(user["user_id"]), "type": "access", "roles": ["ADMIN"]}, timedelta(minutes=15))
    
    async with httpx.AsyncClient() as client:
        res = await client.delete("http://localhost:8080/auth/admin/users/123", headers={"Authorization": f"Bearer {token}"})
        print(res.status_code, res.text)
        
        # Test OPTIONS
        res = await client.options("http://localhost:8080/auth/admin/users/123", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "DELETE"})
        print("OPTIONS", res.status_code, res.headers)

asyncio.run(test())

