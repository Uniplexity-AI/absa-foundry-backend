import asyncio
import httpx
import json
import time

payload = {
    "customers": [
        {
            "customer_id": "CUST00877",
            "churn_probability": 0.85,
            "clv": 15000,
            "segment": "MASS_MARKET",
            "health_score": 25.0
        }
    ]
}

async def run():
    async with httpx.AsyncClient(timeout=180.0) as client:
        t0 = time.time()
        r = await client.post('http://127.0.0.1:8005/decisions/cohort-campaigns', json=payload)
        t1 = time.time()
        print(f"Status: {r.status_code}, Time: {t1-t0:.2f}s")
        print(r.text)

asyncio.run(run())
