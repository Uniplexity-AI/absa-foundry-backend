import re

with open('app/api/routes.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_route = """
class CohortCustomerSummary(BaseModel):
    customer_id: str
    churn_probability: float | None = 0.0
    clv: float | None = 0.0
    segment: str | None = "MASS_MARKET"
    health_score: float | None = 50.0

class CohortCampaignRequest(BaseModel):
    customers: list[CohortCustomerSummary]

@router.post("/cohort-campaigns")
async def generate_cohort_campaigns(request: CohortCampaignRequest):
    \"\"\"Dynamically generate campaign strategies for a cohort using the LLM.\"\"\"
    from app.engines.llm_cohort_engine import LLMCohortEngine
    try:
        engine = LLMCohortEngine(model_name="absa-nba")
        # Convert to dict for the LLM prompt
        customers_data = [c.model_dump() for c in request.customers]
        return await engine.generate_campaigns_async(customers_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/digital-retention")"""

content = content.replace('@router.get("/digital-retention")', new_route.strip('\n'))

if "from pydantic import BaseModel" not in content:
    content = content.replace('from fastapi import', 'from pydantic import BaseModel\nfrom fastapi import')

with open('app/api/routes.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added /cohort-campaigns route")
