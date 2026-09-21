import asyncio
import httpx
import json

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
        r = await client.post('http://localhost:8005/decisions/cohort-campaigns', json=payload)
        print(r.status_code)
        print(r.text)

asyncio.run(run())
