
import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        # 1. Login to get token
        login_res = await client.post("http://localhost:8080/auth/login", json={"username": "admin", "password": "password"})
        if login_res.status_code != 200:
            print("Login failed", login_res.status_code, login_res.text)
            return
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Create a user
        create_res = await client.post("http://localhost:8080/auth/admin/users", json={
            "username": "e2e_test",
            "email": "e2e@ab.com",
            "display_name": "E2E",
            "password": "pass",
            "roles": ["OPERATIONS"]
        }, headers=headers)
        if create_res.status_code != 200:
            print("Create failed", create_res.status_code, create_res.text)
            return
        user_id = create_res.json()["user_id"]
        print("Created user", user_id)
        
        # 3. Delete the user
        del_res = await client.delete(f"http://localhost:8080/auth/admin/users/{user_id}", headers=headers)
        print("Delete res:", del_res.status_code, del_res.text)

asyncio.run(test())

