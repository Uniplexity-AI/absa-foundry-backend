import asyncio
import time
import httpx

async def run():
    async with httpx.AsyncClient(timeout=180.0) as client:
        print("First request...")
        t0 = time.time()
        r1 = await client.get('http://127.0.0.1:8005/decisions/CUST00877/nba')
        t1 = time.time()
        print(f"Status: {r1.status_code}, Time: {t1-t0:.2f}s")
        
        print("Second request...")
        t2 = time.time()
        r2 = await client.get('http://127.0.0.1:8005/decisions/CUST00877/nba')
        t3 = time.time()
        print(f"Status: {r2.status_code}, Time: {t3-t2:.2f}s")

asyncio.run(run())
