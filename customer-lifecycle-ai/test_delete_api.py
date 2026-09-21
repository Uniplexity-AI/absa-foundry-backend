
import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        import sys
        sys.path.append(".")
        from shared.auth.user_repository import UserRepository
        repo = UserRepository()
        conn = repo._pool.getconn()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM iam.users WHERE username = 'testdelapi'")
        user_id = cur.fetchone()[0]
        
        # Get admin token bypass
        cur.execute("SELECT user_id FROM iam.users WHERE username = 'admin' LIMIT 1")
        admin_id = cur.fetchone()[0]
        repo._pool.putconn(conn)
        
        # Generate token directly
        from shared.auth.authenticator import _create_token
        from datetime import timedelta
        token = _create_token({"sub": str(admin_id), "type": "access", "roles": ["ADMIN"]}, timedelta(minutes=15))
        
        res = await client.delete(f"http://localhost:8080/auth/admin/users/{user_id}", headers={"Authorization": f"Bearer {token}"})
        print("Status:", res.status_code)
        print("Body:", res.text)

asyncio.run(test())

