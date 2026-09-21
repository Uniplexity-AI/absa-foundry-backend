import httpx
import asyncio

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
    async with httpx.AsyncClient(timeout=300.0) as client:
        print("Sending request to 8080...")
        r = await client.post('http://127.0.0.1:8005/decisions/cohort-campaigns', json=payload)
        print("Status:", r.status_code)
        print("Response:", r.text[:500])

asyncio.run(run())
