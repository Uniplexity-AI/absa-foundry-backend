import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post('http://127.0.0.1:8009/catalog/campaigns', json={
                "title": "Test",
                "description": "Test description"
            })
            print("Status:", resp.status_code)
            print("Body:", resp.text)
        except Exception as e:
            print("Error:", e)

asyncio.run(test())
